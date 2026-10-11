---
name: local-gemma-harness
description: "Run, monitor, benchmark, and extend the local Gemma 4 26B agent harness and multi-agent swarm on Apple Silicon. Activate when working with LiteRT, on-device Gemma models, terminal agent harnesses, Chain-of-Thought streaming, real-time performance telemetry, or macOS GPU monitoring."
---

# Local Gemma 4 Agent Harness & Multi-Agent Swarm Runbook

This skill encapsulates the exact architecture, scripts, operational workflows, and hard-won engineering patterns for running Google Antigravity agents 100% offline using Google AI Edge LiteRT and Gemma 4 26B on Apple Silicon (M2/M3/M4).

## Architecture Overview

- **Engine**: Google AI Edge LiteRT (`litert-lm`) with Apple Silicon Metal GPU acceleration.
- **Model Checkpoint**: Gemma 4 26B A4B (~14.7 GiB, imported via `litert-lm import` to `~/.litert-lm/models/gemma4-26b/model.litertlm`).
- **SDK**: `google-antigravity` Python SDK (`LiteRTAgentConfig`).
- **TUI Harness**: Terminal User Interface (`harness_tui.py`) with `prompt_toolkit`, forward-only line-buffered streaming (`TerminalMarkdownStreamer`), live Chain-of-Thought reasoning box, turn telemetry footer, and diff preview confirmation.
- **Persistence & Telemetry**: Zero-data-loss session engine (`session_manager.py`) persisting to `transcript.md` (with collapsible `<details>` thought blocks) and `events.jsonl` (with TTFT, decode tok/s, thought metrics, and VRAM).
- **Swarm Architecture**: Sequential multi-agent pipeline (`swarm.py`) executing specialized roles (Planner → Worker → Reviewer) over a single shared model instance in Unified Memory.

## Core Components & Scripts

| Component | Path | Description |
| :--- | :--- | :--- |
| **Agent Launcher** | [`run_tui.sh`](../../../run_tui.sh) | Shell wrapper invoking `.venv/bin/python harness_tui.py "$@"` with argument forwarding. |
| **Interactive TUI** | [`harness_tui.py`](../../../harness_tui.py) | Full-featured REPL, prompt loop, streaming markdown, live `<thought>` parser, tool hooks, and safety gates. |
| **Session Manager** | [`session_manager.py`](../../../session_manager.py) | Atomic session storage, turn telemetry computation, markdown transcripts, and `events.jsonl` audit trails. |
| **Monitor Launcher** | [`run_monitor.sh`](../../../run_monitor.sh) | Shell launcher executing `monitor_m2.py` inside `.venv` to prevent `ModuleNotFoundError: psutil`. |
| **Hardware Monitor** | [`monitor_m2.py`](../../../monitor_m2.py) | Zero-sudo Curses monitor for CPU, RAM, and Apple Silicon `IOAccelerator` GPU % and allocated VRAM. |
| **Multi-Agent Swarm** | [`swarm.py`](../../../swarm.py) | Sequential role handoff pipeline (Planner → Worker → Reviewer) sharing the LiteRT Metal model. *(WIP)* |
| **Diagnostic Test** | [`smoke.py`](../../../smoke.py) | Quick smoke test verifying LiteRT Metal GPU initialization, shader compilation, and basic tool inference. |
| **Session Inspector** | [`view_history.py`](../../../view_history.py) | CLI utility to list sessions, view formatted Markdown transcripts, and prune past sessions. |
| **Unit Tests** | [`tests/`](../../../tests) | Test suite covering session persistence, telemetry logging, thought streamer, and diff safety. |

## Quick Start & Operational Workflows

### 1. Download & Import Model Checkpoint
To import the Gemma 4 26B A4B LiteRT model into the default location:
```bash
.venv/bin/litert-lm import --from-huggingface-repo litert-community/gemma-4-26B-A4B-it-litert-lm gemma-4-26B-A4B-it-gpu.litertlm gemma4-26b
```

### 2. Verify Inference (Compiles Metal Shaders)
Run the diagnostic smoke test (takes ~60–90s on cold start to compile GPU Metal shaders; subsequent runs take ~2–3s):
```bash
.venv/bin/python smoke.py
```

### 3. Launching the Agent
```bash
# Interactive default mode (prompts before write/exec tools)
./run_tui.sh

# Autonomous / YOLO mode (auto-approves tool execution)
./run_tui.sh --yolo

# Scope agent to an external project workspace
./run_tui.sh --workspace /path/to/target-project

# Resume a specific session by list index number (#) or session UUID
./run_tui.sh --resume 1
```

### 4. Real-Time Hardware Monitoring (Zero Sudo)
In a secondary terminal window:
```bash
./run_monitor.sh
```

### 5. In-Chat Slash Commands
Within the TUI REPL:
- `/swarm <task>`: Run the sequential Planner → Worker → Reviewer multi-agent pipeline *(WIP)*.
- `/sessions`: List all saved sessions with index numbers, turns, and timestamps.
- `/resume <#>`: Switch to and resume another session.
- `/delete <#>`: Permanently remove a session directory.
- `/rename <topic>`: Set a custom title for the active session.
- `/info`: Print active session metadata, model path, safety mode, and working directory.
- `/export`: Print paths and byte sizes of `transcript.md` and `events.jsonl`.
- `/clear`: Clear terminal screen and reset conversation history in memory.
- `/exit`: Cleanly save session metadata and exit.

### 6. Automated Verification
Always verify code changes with the test suite:
```bash
.venv/bin/pytest tests/ -v
```

## Critical Architectural Invariants & Hard-Won Learnings

### 1. CustomSystemInstructions vs AppendedSystemInstructions (The Identity Bug)
- **Problem**: When creating `LiteRTAgentConfig`, passing a plain string to `system_instructions` causes `google-antigravity` to treat it as `AppendedSystemInstructions`. The SDK appends these instructions *after* its built-in preamble (`<identity>You are Antigravity...</identity>`), leading Gemma to identify as "Antigravity" instead of Gemma when asked "who are you?".
- **Solution**: Always wrap instructions with `types.CustomSystemInstructions`:
  ```python
  from google.genai import types

  config = LiteRTAgentConfig(
      model=model_path,
      system_instructions=types.CustomSystemInstructions(text=DEFAULT_SYSTEM_INSTRUCTIONS),
      ...
  )
  ```
  This cleanly replaces the SDK default identity with the on-device Gemma identity and explicit Chain-of-Thought prompting instructions.

### 2. Forward-Only Thought Streaming & Reasoning UI
- **Gemma 4 Formats**: Gemma 4 outputs reasoning either inside `<thought>...</thought>` tags or native channel delimiters (`<|channel>thought\n`...`<channel|>`).
- **Terminal UI Streamer**: `TerminalMarkdownStreamer` intercepts these tags mid-stream, buffering thought tokens and formatting them inside a dedicated bordered box:
  ```text
  ┌── 💭 Thinking Process ────────────────────────────────────
  │ Reasoning step 1...
  │ Reasoning step 2...
  └── 💭 Thought for 9.1s, 537 tokens ────────────────────────
  ```
- **Collapsible Transcripts**: In saved `transcript.md` files, thought blocks are converted to standard HTML `<details><summary>💭 <i>Thought Process</i></summary>...</details>` blocks. This keeps Markdown transcripts clean and readable in GitHub, VS Code, and Obsidian.
- **Scrollback Safety**: Forward-only line streaming preserves 100% of native terminal scrollback (unlike screen-redrawing widgets).

### 3. Real-Time Turn Telemetry Instrumentation
- Every turn captures high-resolution timestamps:
  - `start_time`: Time when user prompt was submitted.
  - `first_token_time`: Captured upon arrival of the very first token (calculates TTFT: `first_token_time - start_time`).
  - `end_time`: Turn completion.
  - Decode duration: `end_time - first_token_time`.
  - Decode speed: `tokens / decode_duration` (reported as `⚡ tok/s`).
  - Thought duration & tokens: Exact time and tokens spent inside `<thought>` blocks.
- Telemetry footer displayed after each turn:
  ```text
  ⏱ 14.2s | thought 9.1s, 537 tok | TTFT 0.8s | ⚡ 33.4 tok/s (720 tok) | 🧠 14.8 GB VRAM (GPU 85%) | Turn 2 saved
  ```
- Telemetry is persisted in structured JSON fields in `./sessions/<id>/events.jsonl` and formatted into `transcript.md`.

### 4. Apple Silicon Hardware Telemetry Without Sudo
- **Never use `powermetrics`**: Requires `sudo` and fails silently or prompts for password in subshells.
- **Query IOKit `IOAccelerator`**:
  ```bash
  ioreg -r -c IOAccelerator | grep -E "Device Utilization %|Alloc system memory"
  ```
  Provides instant, non-blocking GPU utilization percentage and byte allocations with zero administrative privileges. Implemented in `session_manager.get_apple_silicon_gpu_metrics()`.

### 5. Terminal Input Navigation (`prompt_toolkit`)
- **Never use `input()` or `console.input()`** on macOS; arrow keys emit raw ANSI escape codes (`^[[A`, `^[[B`).
- Always use `prompt_toolkit.PromptSession()` for full cursor editing, command history, and styled prompts.

### 6. Terminal Scrollback & Responsiveness
- **Never use `rich.live.Live`**: It repaints the screen buffer, truncates text taller than the screen, and destroys native terminal scrollback.
- Use line-buffered forward-only streaming (`TerminalMarkdownStreamer`), which allows the terminal emulator to handle dynamic line re-wrapping cleanly during window resize.

### 7. Non-Destructive Turn Interruption & Atomic Writes
- Pressing `Ctrl+C` halts only the active generation stream, flushes partial output, logs an interrupted turn to disk (`events.jsonl` and `transcript.md`), and keeps the REPL session alive.
- All session metadata writes must use temporary files followed by atomic `os.replace` to prevent corrupted state on unexpected terminations.

### 8. Memory Budget & Multi-Model Concurrency on Apple Silicon (32 GB RAM)
- **Unified Memory Budget**:
  - macOS & Display Services: ~6 GB.
  - Gemma 4 26B A4B: ~14.7 GB static weights + ~2 GB KV-cache = ~16.7 GB.
  - Available Headroom: ~9.3 GB.
- **Secondary Model Concurrency**:
  - A small 2B–3B model (e.g. Qwen 2.5 3B or Gemma 2B 4-bit, ~2.5–3.0 GB) fits in RAM simultaneously.
  - However, running two models *concurrently* splits the Apple Silicon 200 GB/s Metal memory bandwidth, severely degrading inference throughput.
  - **Best Practice**: Use sequential handoffs (`swarm.py` pipeline) where roles execute one after another, or share the single loaded model instance across different role system prompts.
