# Local Gemma 4 Agent Harness & Multi-Agent Swarm

A 100% offline, tool-augmented terminal agent and multi-agent development environment for **Gemma 4 26B** on **Apple Silicon (M2/M3/M4)**. Powered by **Google AI Edge LiteRT (`litert-lm`)** with Metal GPU acceleration and the **Google Antigravity SDK**.

---

## 💎 About Gemma 4

**Gemma** is Google DeepMind's family of lightweight open models built on the same research and technology as Gemini. **Gemma 4** delivers advanced reasoning across text, code, audio, and vision with 140+ language support and long-context windows (128K–256K) optimized for on-device execution.

---

## 💡 Why This Exists

Most local LLM tools (like Ollama or LM Studio) are designed primarily for conversational chat or HTTP APIs. They lack built-in **agentic coding primitives**—native tools for inspecting files, applying targeted code edits, executing shell commands, and sandboxing workspaces.

This harness turns a local Gemma checkpoint into a capable, on-device software engineer that reads, edits, and verifies code directly in your local repositories with zero cloud API keys, zero telemetry, and zero token bills.

---

## ⚡ Core Capabilities

| Capability | What It Does |
| :--- | :--- |
| **100% On-Device Metal Inference** | Runs Gemma 4 26B A4B (~14.7 GiB) directly in Unified Memory with zero external network calls. |
| **Agentic Coding Primitives** | Equipped with native tools: `view_file`, `write_to_file`, `replace_file_content`, and `run_command`. |
| **Interactive Safety & YOLO Mode** | Safe by default: write and shell actions require confirmation (`[y/N/a]`). Pass `--yolo` for autonomous workflows. |
| **Workspace Sandboxing** | Target specific directories with `--workspace <path>`, preventing accidental edits to the harness codebase. |
| **Multi-Agent Swarm Pipeline** | Orchestrates specialized roles (Planner → Worker → Reviewer) sequentially over a single shared model instance *(WIP)*. |
| **Zero-Data-Loss Logging** | Every interaction is logged to both human-readable Markdown (`transcript.md`) and structured JSONL (`events.jsonl`). |
| **Non-Destructive Turn Interruption** | Pressing `Ctrl+C` halts only the current stream, preserves partial output, and keeps the REPL session alive. |
| **Atomic Metadata Writes** | Writes session state via temporary files and `os.replace` to prevent metadata corruption on crashes. |
| **Forward-Only Terminal Streaming** | Preserves 100% native OS scrollback and reflows cleanly without redraw flickering or truncation. |
| **Zero-Sudo Hardware Telemetry** | Queries macOS `IOAccelerator` directly via `monitor_m2.py` for real-time GPU %, VRAM, CPU, and RAM without root access. |
| **Session Management CLI** | Commands to list, resume by numeric index (`--resume 1`), inspect transcripts, and delete past sessions. |

---

## 📊 Performance & Hardware Metrics

Tested on Apple Silicon (**M2 Pro, 32 GB Unified Memory**) running **Gemma 4 26B A4B**:

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Decode Throughput** | **~30 tokens/sec** | Sustained streaming generation speed via Metal GPU. |
| **Cold Start (Initial Load)** | **~60–90 seconds** | One-time compilation of LiteRT Metal GPU shaders on disk. |
| **Warm Start (Subsequent)** | **~2–3 seconds** | Fast memory-mapped weight load into Unified Memory. |
| **Time to First Token (TTFT)** | **~300–800 ms** | Prompt prefill processing (system instructions + tool schemas). |
| **Memory Footprint** | **~14.7 GB static** | Peak usage reaches ~16.5 GB with active KV-cache during multi-turn sessions. |

> [!NOTE]
> **Hardware Guidance**: 24 GB+ Unified Memory is recommended for comfortable headroom with Gemma 4 26B. Machines with 16 GB RAM can run Gemma 2B or 9B variants by passing `--model <path>`.

---

## 🧠 Multi-Agent Swarm Pipeline (`swarm.py`)

> [!WARNING]
> **Work in Progress / Experimental**:
> The sequential role handoff architecture is implemented in `swarm.py` and via `/swarm <task>`, but multi-turn automated evaluation benchmarks are under active development.

Loading multiple 15 GB models simultaneously on a single Mac will trigger out-of-memory errors. The Swarm solves this by running specialized roles **sequentially** over the **same loaded model instance**:

```
[User Objective] ──► [1. PLANNER] ──► [2. WORKER] ──► [3. REVIEWER]
                       (Read-only       (Code edits       (Audits diffs
                        Blueprint)       & commands)       & verifies)
```

Trigger a swarm task inside the TUI REPL:
```text
You [1] > /swarm Add unit tests for session_manager.py and verify coverage
```

---

## 📁 Repository Overview

| File | Purpose |
| :--- | :--- |
| **`harness_tui.py`** | Interactive REPL with `prompt_toolkit`, forward-only streaming, safety gates, and slash commands. |
| **`swarm.py`** | Sequential multi-agent pipeline (Planner → Worker → Reviewer) sharing the LiteRT Metal model. *(WIP)* |
| **`session_manager.py`** | Session persistence engine handling atomic metadata, `events.jsonl` audit trails, and transcripts. |
| **`monitor_m2.py`** | Zero-sudo Curses monitor tracking Apple Silicon GPU utilization %, VRAM allocation, CPU, and RAM. |
| **`view_history.py`** | CLI tool to inspect session tables, view formatted transcripts, and delete past sessions. |
| **`smoke.py`** | Diagnostic script to verify LiteRT Metal GPU initialization and on-device inference. |
| **`run_tui.sh`** | Shell launcher forwarding arguments to the virtual environment. |
| **`tests/`** | Unit test suite covering session persistence, atomic writes, streamer formatting, and backtick safety. |

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/aaarel/local-gemma-harness-and-swarm.git
cd local-gemma-harness-and-swarm

uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt pytest
```

### 2. Verify Inference
```bash
.venv/bin/python smoke.py
```

### 3. Launch the Interactive REPL
```bash
# Safe mode (prompts before write/exec tools)
./run_tui.sh

# Autonomous mode (auto-approves tool execution)
./run_tui.sh --yolo

# Scope the agent to an external project workspace
./run_tui.sh --workspace /path/to/target-project

# Resume a previous session by number (#) or ID
./run_tui.sh --resume 1
```

---

## 💬 In-Chat Slash Commands

* **`/swarm <task>`** — Run the sequential Planner → Worker → Reviewer pipeline *(WIP)*.
* **`/sessions`** — List all saved sessions with index numbers, turns, and timestamps.
* **`/delete <#>`** — Delete a past session from disk.
* **`/rename <topic>`** — Rename the active session title.
* **`/info`** — Display session ID, safety mode, model path, and storage paths.
* **`/export`** — Show file locations and sizes for `transcript.md` and `events.jsonl`.
* **`/clear`** — Clear the terminal screen and reset conversation context.
* **`/exit`** — Cleanly save session metadata and exit.

---

## 🧪 Testing & Quality Assurance

Run the unit test suite:
```bash
pytest tests/
```
Tests validate:
- Atomic file write mechanisms and crash resilience.
- Structured event logging in `events.jsonl`.
- Dynamic backtick collision safety (`safe_code_block`).
- Line-buffered markdown streaming and nested bullet point preservation.

---

## 🔒 Privacy & Security

- **100% Offline**: No network requests or telemetry. Model weights run directly on Apple Silicon Metal.
- **Isolated Sessions**: Conversation histories are kept in `./sessions/` and are ignored by `.gitignore`.
- **Command Guardrails**: Modifying tools (`run_command`, `write_to_file`, `replace_file_content`) require manual user confirmation by default.

---

## 📄 License

MIT License. Built with Google Antigravity & Google AI Edge LiteRT.
