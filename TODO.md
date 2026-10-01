# Future Improvements & Technical Backlog

This backlog records candidate improvements, code review recommendations (including feedback from Gemma 4 self-review), and future enhancements for the harness and swarm.

---

### 1. Architectural & State Management Refactoring
- [ ] **Encapsulate Global Variables into `TUIState` / `AppState`**:
  - **Context**: In `harness_tui.py`, global variables (`active_tools`, `current_streamer`, `yolo_mode`, `current_session`, `prompt_session`) manage runtime state across hooks and the main loop.
  - **Improvement**: Group state into a typed `TUIState` dataclass passed cleanly into SDK hooks (`on_pre_tool`, `on_post_tool`) and command dispatchers. Improves testability and avoids global namespace side effects.

- [ ] **Command Dispatcher Registry (Replace `if/elif` chain)**:
  - **Context**: Slash commands (`/exit`, `/clear`, `/sessions`, `/delete`, `/swarm`, etc.) are dispatched via a cascading `if/elif` block in `harness_tui.py`.
  - **Improvement**: Implement a command pattern / dictionary registry:
    ```python
    COMMAND_REGISTRY = {
        "/clear": handle_clear,
        "/sessions": handle_sessions,
        "/delete": handle_delete,
        "/swarm": handle_swarm,
        ...
    }
    ```
  - **Benefits**: Enables dynamic discovery, automated `/help` command listings, and cleaner addition of future commands.

---

### 2. Code Quality & Defensive Improvements
- [ ] **Pre-Compile Regex Patterns in Streamer**:
  - In `TerminalMarkdownStreamer`, compile bullet and formatting regexes at module level (`re.compile(...)`) rather than re-evaluating patterns inside `_print_line`.
- [ ] **Defensive Logging in Post-Tool Hooks**:
  - Add debug/warning logging if `active_tools.pop(call_id, None)` returns `None` to catch potential synchronization or dropped tool-call notifications.

---

### 3. Swarm Evaluation & Benchmarking
- [ ] **Multi-Agent Swarm Evals**:
  - Create a benchmark script running standard multi-turn coding tasks through `swarm.py` (Planner → Worker → Reviewer).
  - Measure success rate, turn count, and token overhead when all three roles share memory sequentially.
- [ ] **Performance Benchmarking Suite**:
  - Implement a standardized benchmark comparing decode throughput (tokens/sec) and Time to First Token (TTFT) across different context lengths (1k, 4k, 8k tokens).

---

### 4. Modular Packaging (For Future Scale)
- [ ] **Deconstruct `harness_tui.py`**:
  - If the script grows beyond ~400 lines, extract modular components:
    - `streamer.py`: `TerminalMarkdownStreamer` and formatting utilities.
    - `state.py`: `TUIState` and lifecycle hooks.
    - `commands/`: Individual slash command handler functions.

---

### ⚠️ Invariant & Architecture Notice
- **DO NOT replace `TerminalMarkdownStreamer` with `rich.live.Live`**:
  - While recommended by generic LLM reviews, `rich.live.Live` repaints the visible screen buffer in place. On long streaming answers, this destroys native OS terminal scrollback (users cannot scroll up) and causes truncation or screen flickering on window resize. Forward-only line streaming is an intentional architectural invariant.
