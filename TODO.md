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

### 5. Architectural Patterns from Pi & OMA
- [x] **Visual Colorized Diffs on Safety Prompts** *(Implemented)*:
  - Formatted `rich` unified diff preview on file write/replace prompts (`replace_file_content` / `write_to_file`), showing exact line additions/deletions before confirmation.

- [ ] **The `/undo` / `/rewind` Turn Checkpoint System (from Pi)**:
  - **Context**: 26B local models occasionally take wrong turns or produce broken syntax.
  - **Improvement**: Implement an `/undo` or `/rewind` slash command that rolls back the session state in `session_manager.py` (removing the last turn from context and `transcript.md`) and reverts any modified file changes to the previous turn checkpoint.

- [ ] **Aggressive Tool Output Pruning & KV-Cache Protection (from Pi)**:
  - **Context**: Large terminal outputs (e.g., hundreds of lines from `pytest`, build logs, or large file listings) quickly fill the KV-cache and dramatically inflate prefill latency (TTFT) on Apple Silicon.
  - **Improvement**: Persist full outputs to `events.jsonl` on disk, but prune the in-memory context sent to the model: keep the first 10 lines + last 10 lines + exit status (e.g. `[Output truncated: 180 lines, exit code 0]`). This preserves fast prefill (~400ms) across long sessions.

- [ ] **Lean "Core-4" Minimal Tool Optimization (from Pi)**:
  - **Context**: Smaller local models achieve higher accuracy when tool definitions are ruthlessly minimal and unambiguous.
  - **Improvement**: Harden the core 4 primitives (`view_file`, `write_to_file`, `replace_file_content`, `run_command`) with concise, low-token schemas and strict prompt hints to eliminate tool-selection hallucinations.

- [ ] **Pre-Configured Workflow Modes (from OMA / Oh-My-AGY)**:
  - **Context**: Different tasks require different model behaviors (e.g., deep analysis vs. fast code generation).
  - **Improvement**: Add an in-chat mode switcher (e.g., `/mode architect`, `/mode code`, `/mode review`) that dynamically swaps the active `system_instructions` without dropping conversational memory.

---

### ⚠️ Invariant & Architecture Notice
- **DO NOT replace `TerminalMarkdownStreamer` with `rich.live.Live`**:
  - While recommended by generic LLM reviews, `rich.live.Live` repaints the visible screen buffer in place. On long streaming answers, this destroys native OS terminal scrollback (users cannot scroll up) and causes truncation or screen flickering on window resize. Forward-only line streaming is an intentional architectural invariant.
