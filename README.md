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
| **Live Chain-of-Thought Reasoning** | Streams step-by-step thinking in a dedicated UI box (`┌── 💭 Thinking Process ──`), tracking thought duration and tokens (`Thought for 9s, 537 tokens`). |
| **Real-Time Turn Telemetry** | Per-turn metrics in the footer: Time to First Token (TTFT), decode speed (`⚡ tok/s`), tokens produced, and live Apple Silicon VRAM/GPU%. |
| **Agentic Coding Primitives** | Equipped with native tools: `view_file`, `write_to_file`, `replace_file_content`, and `run_command`. |
| **Visual Diff Confirmation** | Colorized unified diff preview on file modifications before prompting for user confirmation. |
| **Interactive Safety & YOLO Mode** | Safe by default: write and shell actions require confirmation (`[y/N/a]`). Pass `--yolo` for autonomous workflows. |
| **Workspace Sandboxing** | Target specific directories with `--workspace <path>`, preventing accidental edits to the harness codebase. |
| **Multi-Agent Swarm Pipeline** | Orchestrates specialized roles (Planner → Worker → Reviewer) sequentially over a single shared model instance *(WIP)*. |
| **Zero-Data-Loss Logging** | Every interaction is logged to both human-readable Markdown (`transcript.md`) with collapsible `<details>` thought blocks and structured JSONL (`events.jsonl`). |
| **Non-Destructive Turn Interruption** | Pressing `Ctrl+C` halts only the current stream, preserves partial output, and keeps the REPL session alive. |
| **Atomic Metadata Writes** | Writes session state via temporary files and `os.replace` to prevent metadata corruption on crashes. |
| **Forward-Only Terminal Streaming** | Preserves 100% native OS scrollback and reflows cleanly without redraw flickering or truncation. |
| **Zero-Sudo Hardware Telemetry** | Queries macOS `IOAccelerator` directly via `./run_monitor.sh` for real-time GPU %, VRAM, CPU, and RAM without root access. |
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

## 💭 Chain-of-Thought Reasoning & Thinking UI

For complex coding, planning, and multi-step problem solving, Gemma reasons step-by-step before delivering answers or calling tools. The harness features a dedicated, forward-only stream parser for internal thoughts (`<thought>` tags and native `<|channel>thought` channels):

```text
┌── 💭 Thinking Process ────────────────────────────────────
│ 1. Inspect session_manager.py to check existing telemetry keys
│ 2. Add thought_tokens parameter with optional None default
│ 3. Update transcript.md writer to format collapsible details
│ 4. Run pytest suite to verify backwards compatibility
└── 💭 Thought for 9.1s, 537 tokens ────────────────────────

Here is the implementation plan and the corresponding diff...
```

* **Live Duration & Token Count**: The thought box footer records exact reasoning time and tokens consumed (matching the `agy` CLI experience: `Thought for 9.1s, 537 tokens`).
* **Collapsible Transcripts**: In saved `transcript.md` records, thought blocks automatically render as HTML `<details><summary>💭 <i>Thought Process</i></summary>...</details>` dropdowns, keeping Markdown documents clean and scannable in GitHub, VS Code, or Obsidian.
* **Scrollback-Safe**: Unlike screen-redrawing libraries, thought streaming preserves 100% of native terminal scrollback.

---

## ⚡ Real-Time Performance Telemetry

Every conversation turn concludes with a rich, single-line telemetry footer tracking on-device Metal inference:

```text
⏱ 14.2s | thought 9.1s, 537 tok | TTFT 0.8s | ⚡ 33.4 tok/s (720 tok) | 🧠 14.8 GB VRAM (GPU 85%) | Turn 2 saved
```

| Telemetry Metric | What It Measures |
| :--- | :--- |
| **`⏱ 14.2s`** | Total wall-clock time elapsed from user prompt submission to final token flush. |
| **`thought 9.1s, 537 tok`** | Time and token budget spent inside `<thought>` reasoning blocks. |
| **`TTFT 0.8s`** | **Time to First Token** (prefill latency): time until the initial token streams from Metal. |
| **`⚡ 33.4 tok/s`** | Pure decode throughput: tokens generated per second after prefill completion. |
| **`(720 tok)`** | Total tokens generated in the turn. |
| **`🧠 14.8 GB VRAM`** | Real-time Apple Silicon Unified Memory allocated by `IOAccelerator` (zero sudo). |
| **`(GPU 85%)`** | Instantaneous Metal GPU core utilization percentage. |
| **`Turn 2 saved`** | Confirms atomic state persistence to disk. |

All metrics are recorded as structured fields in `./sessions/<id>/events.jsonl` for automated benchmarking.

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
| **`harness_tui.py`** | Interactive REPL with `prompt_toolkit`, forward-only streaming, reasoning UI, safety gates, and slash commands. |
| **`swarm.py`** | Sequential multi-agent pipeline (Planner → Worker → Reviewer) sharing the LiteRT Metal model. *(WIP)* |
| **`session_manager.py`** | Session persistence engine handling atomic metadata, telemetry logging, `events.jsonl` audit trails, and transcripts. |
| **`monitor_m2.py`** | Zero-sudo Curses monitor tracking Apple Silicon GPU utilization %, VRAM allocation, CPU, and RAM. |
| **`run_monitor.sh`** | Safe shell launcher invoking `monitor_m2.py` inside the project virtual environment. |
| **`view_history.py`** | CLI tool to inspect session tables, view formatted transcripts, and delete past sessions. |
| **`smoke.py`** | Diagnostic script to verify LiteRT Metal GPU initialization and on-device inference. |
| **`run_tui.sh`** | Shell launcher forwarding arguments to the virtual environment. |
| **`tests/`** | Unit test suite covering session persistence, telemetry logging, thought streaming, and diff safety. |

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

### 2. Download Gemma 4 26B Checkpoint
Download and import the optimized on-device LiteRT checkpoint directly into `~/.litert-lm/models/gemma4-26b/`:
```bash
.venv/bin/litert-lm import --from-huggingface-repo litert-community/gemma-4-26B-A4B-it-litert-lm gemma-4-26B-A4B-it-gpu.litertlm gemma4-26b
```

### 3. Verify Inference
Run the diagnostic smoke test (compiles Metal GPU shaders on initial run):
```bash
.venv/bin/python smoke.py
```

### 4. Launch the Interactive REPL & Monitor
```bash
# Terminal 1: Safe mode (prompts before write/exec tools)
./run_tui.sh

# Autonomous mode (auto-approves tool execution)
./run_tui.sh --yolo

# Scope the agent to an external project workspace
./run_tui.sh --workspace /path/to/target-project

# Resume a previous session by number (#) or ID
./run_tui.sh --resume 1

# Terminal 2 (optional): Live Apple Silicon GPU / VRAM monitor (zero sudo)
./run_monitor.sh
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
- Structured event logging in `events.jsonl` with full turn performance telemetry.
- Dynamic backtick collision safety (`safe_code_block`).
- Line-buffered markdown streaming and nested bullet point preservation.
- Live reasoning block formatting (`<thought>` streaming) and token counting.
- Collapsible `<details>` thought formatting in Markdown transcripts.
- Visual unified diff preview rendering on file replacements and writes.

---

## 🔒 Privacy & Security

- **100% Offline**: No network requests or telemetry. Model weights run directly on Apple Silicon Metal.
- **Isolated Sessions**: Conversation histories are kept in `./sessions/` and are ignored by `.gitignore`.
- **Command Guardrails**: Modifying tools (`run_command`, `write_to_file`, `replace_file_content`) require manual user confirmation by default.

---

## 📄 License

MIT License. Built with Google Antigravity & Google AI Edge LiteRT.
