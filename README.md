# Local Gemma 4 & Antigravity TUI Harness

A high-performance, 100% offline agentic coding harness and terminal environment for **Gemma 4 26B** running on **Apple Silicon (M2/M3/M4)** using **Google AI Edge LiteRT (`litert-lm`)** with Metal GPU acceleration and the **Google Antigravity SDK**.

---

## 🌟 Key Features

### 1. 100% On-Device & Zero Cloud Dependencies
* Runs Gemma 4 26B (`gemma-4-26B-A4B-it-gpu.litertlm`, ~14.7 GiB) entirely locally in Unified Memory.
* Hardware-accelerated inference via Apple Silicon **Metal GPU**.
* Zero external API calls, zero telemetry, and zero recurring cloud costs.
* **Model Flexibility**: The harness can be easily pointed to other models across the Gemma family (e.g., Gemma 2B, 7B, 9B). *Note: This repository was actively tested, tuned, and verified for Gemma 4 26B A4B; running other variants or custom quantizations is fully supported via LiteRT, but may require minor tweaking (e.g. KV-cache capacity or compaction threshold adjustments).*

### 2. Forward-Only Terminal Streaming (`TerminalMarkdownStreamer`)
* Traditional TUI live-screen renderers (e.g. `rich.live.Live`) redraw the visible screen buffer, causing line truncation, flickering, and breaking terminal scrollback.
* Our forward-only line-buffered streamer writes directly to stdout:
  * **100% Native Scrollback**: Scroll all the way to the top of long conversations.
  * **Responsive Terminal Reflow**: Automatically wraps and reflows text dynamically as terminal windows are resized.
  * **Structured Code Fencing**: Renders clean box-drawing code borders (`┌── code ... └──`) with distinct syntax colors.

### 3. Persistent Session Management & Zero Data Loss
* Conversations are automatically indexed and isolated into `./sessions/<session_id>/`.
* Trajectory databases and Antigravity memory are preserved across restarts (`SessionContinuationMode.CREATE_OR_RESUME`).
* **Human-Readable Markdown Transcripts**: Automatically generates `transcript.md` per session with turn-by-turn timing metrics (`⏱ Worked for Xs`).
* **Graceful Interrupts**: Hitting `Ctrl+C` cleanly saves the session state and prints an immediate resume command.
* **1-Based Numeric Resumption**: Resume past sessions easily by number (e.g., `./run_tui.sh --resume 1`).

### 4. Zero-Sudo Apple Silicon Telemetry (`monitor_m2.py`)
* Standard macOS tools like `powermetrics` strictly require `sudo` and fail in non-interactive environments.
* Our monitor queries the macOS IOKit `IOAccelerator` service directly:
  * Real-time **GPU Utilization %**
  * Real-time **Allocated GPU Memory (GB)**
  * Real-time **CPU & RAM usage**
  * Non-blocking (~5ms) and requires **zero root/administrative privileges**.

### 5. SDK Lifecycle Hooks & Tool Observability
* Built on the `google-antigravity` SDK with custom tool execution hooks:
  * `@hooks.pre_tool_call_decide`: Real-time notification when tools execute (`⚡ Executing command: ...`).
  * `@hooks.post_tool_call`: Live execution duration measurement (`✓ Tool completed (1.2s)`).

---

## 📁 Repository Structure

| File | Description |
| :--- | :--- |
| **`harness_tui.py`** | Main interactive terminal agent harness featuring `prompt_toolkit`, forward-only streaming, session lifecycle management, and in-chat slash commands. |
| **`session_manager.py`** | Dedicated session management layer handling session directories, metadata tracking, transcript writing, and numeric index resolution. |
| **`run_tui.sh`** | Native bash launcher forwarding command-line arguments to the Python virtual environment. |
| **`monitor_m2.py`** | Standalone Curses-based real-time Apple Silicon GPU, CPU, and RAM utilization monitor (zero-sudo). |
| **`view_history.py`** | CLI tool to inspect past sessions, turn counters, and resume commands in a formatted Rich table. |
| **`test_inference.py`** | Lightweight script to verify LiteRT Metal GPU compilation and basic inference. |
| **`llm_observer.py`** | Minimal console observer for system health and GPU memory stats. |
| **`AGENTS.md`** | System rules, learnings, architectural constraints, and operational runbook. |

---

## 🚀 Quick Start

### Prerequisites
* **Hardware**: Apple Silicon Mac (M1/M2/M3/M4 with 24 GB+ Unified Memory recommended for the 26B model).
* **Python**: Python 3.11 provisioned via `uv` or `venv`.
* **Model**: Gemma 4 26B A4B registered at `~/.litert-lm/models/gemma4-26b/model.litertlm` (or another Gemma `.litertlm` checkpoint).

> [!TIP]
> **Swapping Models**: You can easily swap the active model by changing `MODEL_PATH` at the top of `harness_tui.py`. While this harness is tested, tuned, and verified for **Gemma 4 26B A4B**, other models in the Gemma family (2B, 7B, 9B, etc.) can be loaded via LiteRT. Keep in mind that different sizes or quantizations may require minor tuning (such as adjusting KV-cache buffer allocations or context compaction thresholds in `LiteRTAgentConfig`).

### Setup
```bash
# 1. Clone repository
git clone https://github.com/aaarel/local-gemma-harness-and-swarm.git
cd local-gemma-harness-and-swarm

# 2. Create virtual environment & install dependencies
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
# (or: pip install -r requirements.txt)
```

---

## 💬 Usage

### 1. Launching the Interactive TUI
```bash
# Interactive mode (prompts to resume recent session or start new)
./run_tui.sh

# Start a brand new session immediately
./run_tui.sh --new

# Resume the most recent session directly
./run_tui.sh --resume

# Resume a specific session by number (#) or ID
./run_tui.sh --resume 1

# List all saved sessions
./run_tui.sh --list
```

### 2. Monitoring Hardware Side-by-Side
Open a separate terminal pane alongside your chat session:
```bash
.venv/bin/python monitor_m2.py
```

### 3. In-Chat Slash Commands
Inside the running TUI harness:
* **`/sessions`** — Display a table of all saved sessions with turn counts and numbers.
* **`/rename <topic>`** — Rename the current session topic (e.g. `/rename GCP DNS Design`).
* **`/info`** — Display active session ID, trajectory paths, and artifact storage directories.
* **`/export`** — Show the absolute path and stats for the markdown `transcript.md`.
* **`/history`** — View the recent prompt history list.
* **`/clear`** — Reset the current context buffer.
* **`/exit`** — Cleanly save session metadata and exit.

---

## 🔒 Privacy & Security

This repository is designed from the ground up to keep your local data private:
* Personal conversation histories and trajectories are stored in `./sessions/` and are strictly ignored by `.gitignore`.
* Local shell and prompt histories (`prompt_history.txt`) are excluded from version control.
* No credentials, keys, or API tokens are needed or stored anywhere in this codebase.

---

## 📄 License
MIT License. Built with Google Antigravity & Google AI Edge LiteRT.
