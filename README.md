# Local Gemma 4 Agent Harness & Multi-Agent Swarm

An offline, tool-augmented terminal agent and multi-agent development environment for **Gemma 4 26B** on **Apple Silicon (M2/M3/M4)**. Powered by **Google AI Edge LiteRT (`litert-lm`)** with Metal GPU acceleration and the **Google Antigravity SDK**.

---

## 💡 Why This Exists

Most local LLM tools (such as Ollama, LM Studio, or llama.cpp) provide raw chat interfaces or HTTP endpoints, but lack built-in **agentic coding primitives**—tools for file viewing, incremental file editing, command execution, workspace sandboxing, and audit logging.

This project bridges that gap by providing:
1. **Agentic Tool Execution**: Equips local Gemma models with native system tools (file inspection, code editing, shell execution) to perform real engineering tasks on your local disk.
2. **Interactive Safety Controls**: A granular security gate requiring confirmation (`[y/N/a]`) before write or execution actions, paired with workspace isolation.
3. **Hardware-Conscious Swarm**: A sequential multi-agent pipeline (Planner → Worker → Reviewer) designed to fit within Apple Silicon Unified Memory without triggering OOM errors.
4. **Complete Privacy**: Zero cloud calls, zero telemetry, and zero third-party APIs. Your code and prompts stay strictly on your local machine.

---

## ⚡ Harness Capabilities & Features

| Capability | Description |
| :--- | :--- |
| **100% On-Device Metal Inference** | Runs Gemma 4 26B A4B (~14.7 GiB) directly in Unified Memory using Google AI Edge LiteRT with Metal GPU acceleration. |
| **Agentic Coding Tools** | Native tool support for `view_file`, `write_to_file`, `replace_file_content`, and `run_command`. |
| **Interactive Safety & YOLO Mode** | Safe by default: write and shell actions prompt `[y/N/a(lways)]`. Pass `--yolo` for autonomous, unattended workflows. |
| **Workspace Sandboxing** | Target specific directories via `--workspace <path>`, preventing the agent from modifying the harness codebase itself. |
| **Multi-Agent Swarm Pipeline** | Orchestrates specialized roles (Planner → Worker → Reviewer) sequentially over a single model instance *(WIP / Experimental)*. |
| **Zero-Data-Loss Session Logging** | Every interaction is logged to both human-readable Markdown (`transcript.md`) and structured JSONL (`events.jsonl`). |
| **Non-Destructive Turn Interruption** | Pressing `Ctrl+C` halts only the active generation, preserves partial output to disk, and keeps the REPL session alive. |
| **Atomic Metadata Persistence** | State updates write to temporary files before atomic `os.replace` to safeguard against corruption during sudden exits. |
| **Forward-Only Terminal Streaming** | Line-buffered streaming preserves 100% native OS terminal scrollback and supports dynamic terminal resizing without redraw artifacts. |
| **Zero-Sudo Hardware Telemetry** | Standalone IOKit-based dashboard (`monitor_m2.py`) displays real-time GPU %, allocated VRAM (GB), CPU %, and RAM without root privileges. |
| **Session Management & CLI Utilities** | Dedicated commands to list, resume by numeric index (`--resume 1`), inspect transcripts, and delete past sessions. |

---

## 🧠 Multi-Agent Swarm Pipeline (`swarm.py`)

> [!WARNING]
> **Work in Progress / Experimental**:
> The sequential role handoff architecture is implemented and operational in `swarm.py` and via `/swarm <task>`, but multi-turn automated evaluation and self-correction benchmarks are under active development. Feedback and contributions are welcome.

### How It Works
Loading multiple 15 GB models simultaneously on a single 32 GB Mac will exhaust Unified Memory and cause kernel panics or swap thrashing. The Swarm solves this by running specialized roles **sequentially** over the **same loaded model instance**:

```
[User Objective]
       │
       ▼
┌──────────────┐
│   PLANNER    │ ── Inspects workspace (read-only) & drafts technical specification
└──────────────┘
       │
       ▼
┌──────────────┐
│    WORKER    │ ── Implements code changes & edits files per specification
└──────────────┘
       │
       ▼
┌──────────────┐
│   REVIEWER   │ ── Audits diffs, runs test commands & issues PASS/FAIL verdict
└──────────────┘
```

Trigger a swarm task directly inside the TUI REPL:
```text
You [1] > /swarm Add unit tests for session_manager.py and verify coverage
```

---

## 📁 Repository Structure

| File | Description |
| :--- | :--- |
| **`harness_tui.py`** | Primary interactive REPL featuring `prompt_toolkit`, forward-only streaming, safety gates, and slash commands. |
| **`swarm.py`** | Sequential multi-agent pipeline (Planner → Worker → Reviewer) sharing the LiteRT Metal model. *(WIP)* |
| **`session_manager.py`** | Session persistence engine handling atomic metadata, `events.jsonl` audit trails, and transcripts. |
| **`monitor_m2.py`** | Zero-sudo Curses monitor tracking Apple Silicon GPU utilization %, VRAM allocation, CPU, and RAM. |
| **`view_history.py`** | CLI tool to inspect session tables, view formatted transcripts, and delete past sessions. |
| **`smoke.py`** | Quick diagnostic script to verify LiteRT Metal GPU compilation and local inference. |
| **`run_tui.sh`** | Shell wrapper forwarding CLI arguments to the project virtual environment. |
| **`pyproject.toml`** | Packaging specification declaring dependencies and the `gemma-harness` command entrypoint. |
| **`tests/`** | Unit test suite covering session persistence, atomic writes, streamer formatting, and backtick safety. |
| **`AGENTS.md`** | Engineering rules, architectural invariants, and hardware-specific learnings. |

---

## 🚀 Quick Start

### Hardware & Software Requirements
- **Hardware**: Apple Silicon Mac (M1/M2/M3/M4). 24 GB–32 GB Unified Memory recommended for Gemma 4 26B; 16 GB Macs can run Gemma 2B or 9B variants.
- **Python**: Python 3.11 provisioned via `uv` or `venv`.
- **Model**: Gemma 4 26B A4B registered at `~/.litert-lm/models/gemma4-26b/model.litertlm` (or any compatible Gemma `.litertlm` checkpoint).

> [!TIP]
> **Swapping Models**: You can load other Gemma variants using `--model /path/to/model.litertlm` or by setting `DEFAULT_MODEL_PATH` in `harness_tui.py`. While verified primarily on Gemma 4 26B A4B, LiteRT supports other checkpoints in the Gemma family.

### Installation
```bash
# 1. Clone repository
git clone https://github.com/aaarel/local-gemma-harness-and-swarm.git
cd local-gemma-harness-and-swarm

# 2. Set up virtual environment and install dependencies
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt pytest
```

### Verification Smoke Test
Before starting interactive sessions, verify that LiteRT loads the model and compiles Metal shaders:
```bash
.venv/bin/python smoke.py
```

---

## 💬 Usage Guide

### 1. Launching the Interactive TUI
```bash
# Safe interactive mode (prompts before write/exec tools)
./run_tui.sh

# Autonomous mode (auto-approves tool execution)
./run_tui.sh --yolo

# Scope the agent to an external project workspace
./run_tui.sh --workspace /path/to/target-project

# Resume a previous session by numeric index (#) or session ID
./run_tui.sh --resume 1

# List all saved sessions on disk
./run_tui.sh --list
```

### 2. In-Chat Slash Commands
* **`/swarm <task>`** — Run the sequential Planner → Worker → Reviewer pipeline. *(WIP)*
* **`/sessions`** — List all saved sessions with index numbers, turns, and dates.
* **`/delete <#>`** — Delete a session folder from disk.
* **`/rename <topic>`** — Rename the active session title (e.g. `/rename Database Refactor`).
* **`/info`** — Display session ID, safety mode, model path, and storage paths.
* **`/export`** — Show paths and sizes for `transcript.md` and `events.jsonl`.
* **`/clear`** — Clear the terminal screen and reset conversation context.
* **`/exit`** — Save metadata atomically and exit.

### 3. Real-Time Hardware Monitoring
To monitor GPU load and Unified Memory allocation while the agent runs, launch the monitor in an adjacent terminal split:
```bash
.venv/bin/python monitor_m2.py
```

### 4. Viewing Past Session Transcripts
```bash
# List sessions
.venv/bin/python view_history.py

# Print transcript of session #1
.venv/bin/python view_history.py -t 1

# Delete session #2
.venv/bin/python view_history.py -d 2
```

---

## 🧪 Testing & Quality Assurance

Run the test suite:
```bash
pytest tests/
```
Tests validate:
- Atomic file write mechanisms and crash resilience.
- Structured event logging in `events.jsonl`.
- Dynamic backtick collision safety (`safe_code_block`).
- Line-buffered markdown streaming and nested bullet point preservation.

---

## 🔒 Privacy & Data Isolation

- **Zero Cloud Calls**: Model weights run locally on Apple Silicon Metal; no telemetry or data packets leave your device.
- **Isolated Session Storage**: Transcripts and trajectories are saved under `./sessions/` and are excluded from Git via `.gitignore`.
- **Command & Prompt History**: REPL history (`prompt_history.txt`) is kept local and untracked.
- **Permission Guardrails**: Modification tools (`run_command`, `write_to_file`, `replace_file_content`) require manual user confirmation by default.

---

## 📄 License

MIT License. Built with Google Antigravity & Google AI Edge LiteRT.
