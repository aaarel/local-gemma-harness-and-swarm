# Local Gemma 4 & Antigravity TUI Harness + Swarm

A high-performance, 100% offline agentic coding harness, multi-agent swarm, and terminal environment for **Gemma 4 26B** running on **Apple Silicon (M2/M3/M4)** using **Google AI Edge LiteRT (`litert-lm`)** with Metal GPU acceleration and the **Google Antigravity SDK**.

---

## 🌟 Key Features

### 1. 100% On-Device & Zero Cloud Dependencies
* Runs Gemma 4 26B (`gemma-4-26B-A4B-it-gpu.litertlm`, ~14.7 GiB) entirely locally in Unified Memory.
* Hardware-accelerated inference via Apple Silicon **Metal GPU**.
* Zero external API calls, zero telemetry, and zero recurring cloud costs.
* **Model Flexibility**: The harness can be easily pointed to other models across the Gemma family (e.g., Gemma 2B, 7B, 9B). *Note: This repository was actively tested, tuned, and verified for Gemma 4 26B A4B; running other variants or custom quantizations is fully supported via LiteRT, but may require minor parameter adjustments (e.g. KV-cache capacity or compaction threshold adjustments).*

### 2. Multi-Agent Swarm Pipeline (`swarm.py`)
* Solves the 15 GB VRAM memory constraint on Apple Silicon by coordinating multiple specialized roles (**Planner → Worker → Reviewer**) that take turns over a **single shared LiteRT engine**:
  * **Planner**: Analyzes the objective, inspects the codebase with read-only tools, and crafts an actionable task plan.
  * **Worker / Builder**: Executes the plan, creates/edits files, and implements the code.
  * **Reviewer / QA**: Audits diffs, runs test commands, and issues a final PASS/FAIL verdict with constructive feedback.
* Trigger live in chat with `/swarm <objective>`.

### 3. Interactive Safety Controls & `--yolo` Flag
* **Protected by Default**: Write and execution tools (`run_command`, `write_to_file`, `replace_file_content`) prompt for interactive confirmation `[y/N/a(lways)]` before running.
* **Autonomous Mode**: Pass `--yolo` at startup or type `a` in prompt to grant autonomous tool execution for the session.
* Read-only tools (`view_file`, etc.) remain automatic for a fluid developer experience.

### 4. True Zero-Data-Loss Architecture & Event Logging
* **Turn-Level Cancellation**: Pressing `Ctrl+C` mid-generation stops the current stream, preserves the partial answer, and keeps your REPL session alive without process death.
* **Atomic Metadata Writes**: Uses temporary files with atomic `os.replace` to prevent metadata corruption on abrupt termination.
* **Structured Event Logging (`events.jsonl`)**: Records every user prompt, model response, tool call, argument payload, execution timing, and permission decision alongside human-readable `transcript.md`.
* **Collison-Free Code Fencing**: Safely wraps user prompts containing arbitrary backticks without breaking markdown fences.
* **1-Based Numeric Resumption**: Resume past sessions easily by number (e.g., `./run_tui.sh --resume 1`).

### 5. Forward-Only Terminal Streaming (`TerminalMarkdownStreamer`)
* Traditional TUI live-screen renderers (e.g. `rich.live.Live`) redraw the visible screen buffer, causing line truncation, flickering, and breaking terminal scrollback.
* Our forward-only line-buffered streamer writes directly to stdout:
  * **100% Native Scrollback**: Scroll all the way to the top of long conversations.
  * **Responsive Terminal Reflow**: Automatically wraps and reflows text dynamically as terminal windows are resized.
  * **Regex-Preserved Formatting**: Fully preserves nested bullet indentation and bold (`**Bold**`) markdown markers without text stripping.

### 6. Zero-Sudo Apple Silicon Telemetry (`monitor_m2.py`)
* Standard macOS tools like `powermetrics` strictly require `sudo` and fail in non-interactive environments.
* Our monitor queries the macOS IOKit `IOAccelerator` service directly:
  * Real-time **GPU Utilization %**
  * Real-time **Allocated GPU Memory (GB)**
  * Real-time **CPU & RAM usage**
  * Non-blocking (~5ms) and requires **zero root/administrative privileges**.

---

## 📁 Repository Structure

| File | Description |
| :--- | :--- |
| **`harness_tui.py`** | Main interactive terminal agent harness featuring `prompt_toolkit`, forward-only streaming, safety confirmations, session management, and slash commands. |
| **`swarm.py`** | Multi-agent swarm orchestrator (Planner → Worker → Reviewer) sharing the LiteRT Metal GPU model in memory. |
| **`session_manager.py`** | Dedicated session management layer handling atomic metadata writes, structured `events.jsonl` logging, transcripts, and numeric index resolution. |
| **`monitor_m2.py`** | Standalone Curses-based real-time Apple Silicon GPU, CPU, and RAM utilization monitor (zero-sudo). |
| **`view_history.py`** | CLI tool to inspect past sessions, print transcripts, and delete sessions. |
| **`smoke.py`** | Lightweight smoke verification script for LiteRT runtime compilation and test inference. |
| **`run_tui.sh`** | Native bash launcher forwarding command-line arguments to the Python virtual environment. |
| **`pyproject.toml`** | Modern packaging configuration and CLI script entry points. |
| **`tests/`** | Pytest unit test suite covering session persistence, atomic writes, streamer formatting, and backtick safety. |
| **`AGENTS.md`** | System guidelines, learnings, architectural constraints, and operational runbook. |

---

## 🚀 Quick Start

### Prerequisites
* **Hardware**: Apple Silicon Mac (M1/M2/M3/M4 with 24 GB+ Unified Memory recommended for the 26B model).
* **Python**: Python 3.11 provisioned via `uv` or `venv`.
* **Model**: Gemma 4 26B A4B registered at `~/.litert-lm/models/gemma4-26b/model.litertlm` (or another Gemma `.litertlm` checkpoint).

> [!TIP]
> **Swapping Models**: You can easily swap the active model with `--model /path/to/model.litertlm` or by changing `DEFAULT_MODEL_PATH` in `harness_tui.py`. While this harness is tested, tuned, and verified for **Gemma 4 26B A4B**, other models in the Gemma family (2B, 7B, 9B, etc.) can be loaded via LiteRT.

### Setup
```bash
# 1. Clone repository
git clone https://github.com/aaarel/local-gemma-harness-and-swarm.git
cd local-gemma-harness-and-swarm

# 2. Create virtual environment & install dependencies
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt pytest
```

---

## 💬 Usage

### 1. Launching the Interactive TUI
```bash
# Interactive mode (protected write permissions by default)
./run_tui.sh

# Autonomous execution (YOLO mode - auto-approves tool calls)
./run_tui.sh --yolo

# Run against a specific external project workspace
./run_tui.sh --workspace /path/to/my-project

# Resume a specific session by number (#) or ID
./run_tui.sh --resume 1

# List all saved sessions
./run_tui.sh --list
```

### 2. Multi-Agent Swarm Mode
Inside the TUI chat prompt:
```text
You [1] > /swarm Refactor our database adapter to add connection pooling
```
The Planner will draft the specifications, the Worker will implement the code, and the Reviewer will inspect and deliver verification feedback.

### 3. Monitoring Hardware Side-by-Side
Open a separate terminal pane alongside your chat session:
```bash
.venv/bin/python monitor_m2.py
```

### 4. In-Chat Slash Commands
* **`/swarm <task>`** — Launch the multi-agent Planner → Worker → Reviewer pipeline.
* **`/sessions`** — Display a table of all saved sessions with turn counts and numbers.
* **`/delete <#>`** — Delete a past session from disk.
* **`/rename <topic>`** — Rename the current session topic (e.g. `/rename GCP DNS Design`).
* **`/info`** — Display active session ID, safety mode, and storage directories.
* **`/export`** — Show the absolute path and stats for the markdown `transcript.md` and `events.jsonl`.
* **`/clear`** — Clean the screen view and begin a fresh context sequence.
* **`/exit`** — Cleanly save session metadata and exit.

---

## 🧪 Running Unit Tests
```bash
pytest tests/
```

---

## 🔒 Privacy & Security

This repository is designed from the ground up to keep your local data private:
* Personal conversation histories, trajectories, and events are stored in `./sessions/` and are strictly ignored by `.gitignore`.
* Local shell and prompt histories (`prompt_history.txt`) are excluded from version control.
* Safety policy confirms execution and file-write commands by default to prevent accidental modifications.

---

## 📄 License
MIT License. Built with Google Antigravity & Google AI Edge LiteRT.
