---
name: local-gemma-harness
description: "Run, monitor, and extend the local Gemma 4 26B agent with the Antigravity TUI harness on Apple Silicon. Activate when working with local LLMs, LiteRT, terminal harnesses, or on-device GPU monitoring."
---

# Local Gemma 4 & Antigravity Harness Runbook

This skill encapsulates the exact architecture, scripts, and best practices for running Google Antigravity agents completely offline using LiteRT and Gemma 4 26B on Apple Silicon.

## Architecture Overview

- **Engine**: Google AI Edge LiteRT (`litert-lm`) with Apple Silicon Metal GPU acceleration.
- **Model**: `gemma-4-26B-A4B-it-gpu.litertlm` (~14.7 GiB, registered at `~/.litert-lm/models/gemma4-26b/model.litertlm`).
- **SDK**: `google-antigravity` Python SDK (`LiteRTAgentConfig`).
- **Harness**: Terminal User Interface (`harness_tui.py`) with `prompt_toolkit` and `rich.live.Live(Markdown(...))`.

## Core Components

1. **Launcher**: [`run_tui.sh`](../../run_tui.sh)
   - Directly executes `.venv/bin/python harness_tui.py "$@"`.
2. **Interactive TUI**: [`harness_tui.py`](../../harness_tui.py)
   - Multi-turn interactive conversation loop.
   - Tool execution hooks (`@hooks.pre_tool_call_decide`, `@hooks.post_tool_call`).
   - Live in-place markdown rendering via `rich.live.Live(Markdown(...))`.
   - Arrow-key navigation & history via `prompt_toolkit.PromptSession()`.
   - Elapsed turn timing (`⏱ Worked for Xs`).
3. **M2 Pro Hardware Monitor**: [`monitor_m2.py`](../../monitor_m2.py)
   - Real-time CPU, RAM, GPU utilization %, and GPU allocated memory.
   - Uses zero-sudo `ioreg -r -c IOAccelerator`.

## How to Run

```bash
# 1. Start the interactive local agent
./run_tui.sh

# 2. In a separate terminal, monitor hardware utilization (zero sudo)
.venv/bin/python monitor_m2.py
```

## Troubleshooting & Key Patterns

### Arrow Keys Printing Escape Sequences (`^[[A`)
- Standard `input()` in Python fails on macOS with raw escape codes.
- Always use `prompt_toolkit.PromptSession()`.

### Terminal Scrollback & Narrow Window Responsiveness
- Do not use in-place screen redrawing (like `rich.live.Live`), which crops text taller than the screen and locks wrap width.
- Use forward-only line streaming (`TerminalMarkdownStreamer`):
  - Preserves 100% of native terminal scrollback (you can scroll up to the very beginning).
  - Fully responsive: terminal emulator handles dynamic line wrapping as the window resizes.
  - Styles code blocks with `┌── code` fences and headers in bold yellow.

### Apple Silicon GPU Monitoring Without Sudo
- Avoid `sudo powermetrics`.
- Query IOKit directly:
  ```bash
  ioreg -r -c IOAccelerator | grep -E "Device Utilization %|Alloc system memory"
  ```
