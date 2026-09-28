# Local LLM Project: Gemma 4 & Antigravity Harness

## Hardware & Runtime Architecture
- **Hardware**: Apple M2 Pro (Apple Silicon ARM64), 32 GB Unified Memory.
- **Model**: Gemma 4 26B A4B (`~/.litert-lm/models/gemma4-26b/model.litertlm`, ~14.7 GiB).
- **Inference Runtime**: Google AI Edge LiteRT (`litert-lm`), Metal GPU backend (100% offline, zero cloud calls).
- **Python Environment**: Python 3.11 provisioned via `uv` located at `.venv/bin/python`.

## Critical System Guidelines & Hard-Won Learnings

### 1. Terminal Inputs & TUI Navigation
- **Never use plain Python `input()` or `console.input()`** for interactive terminal agents on macOS; it produces raw escape sequences like `^[[A` on arrow key presses.
- **Always use `prompt_toolkit.PromptSession()`**:
  - Provides native left/right cursor editing and up/down command history recall.
  - Allows styled prompt labels and typed text (e.g. bright cyan for user inputs).

### 2. Output Streaming & Terminal Scrollback
- **Do not use in-place screen-redrawing (`rich.live.Live`) for long AI streams**:
  - `Live` repaints the visible screen buffer, which crops lines exceeding terminal height, breaks terminal scrollback (you cannot scroll up), and locks width on narrow windows.
- **Use Forward-Only Streaming (`TerminalMarkdownStreamer`)**:
  - Writes directly to standard output line-by-line.
  - Guarantees 100% native OS scrollback preservation (scroll up to the very start).
  - Terminal emulator automatically reflows text dynamically across any window width.
  - Formats markdown code fences (`┌── code ... └──`), bold headers, and bullet points with zero duplication.

### 3. Agent Tool Hooks & Timing
- Register SDK hooks in `LiteRTAgentConfig(hooks=[on_pre_tool, on_post_tool])`:
  - `@hooks.pre_tool_call_decide`: Intercept `types.ToolCall` and display `⚡ Executing command: ...` or `⚡ Viewing file: ...`.
  - `@hooks.post_tool_call`: Display `✓ Tool completed (Xs)`.
- Measure turn duration from user prompt to stream completion: `⏱ Worked for Xs`.

### 4. Apple Silicon GPU Metrics (Zero-Sudo)
- **Do not use `powermetrics`**: It strictly requires `sudo` and fails inside non-interactive subprocess calls.
- **Use macOS IOKit `IOAccelerator`**:
  - Run `ioreg -r -c IOAccelerator` to extract `"Device Utilization %"` and `"Alloc system memory"`.
  - Fast (~5ms), non-blocking, and requires zero administrative privileges.

## Running the Components
- **TUI Chat Harness**: `./run_tui.sh` (or `.venv/bin/python harness_tui.py`)
- **System Monitor**: `.venv/bin/python monitor_m2.py`
