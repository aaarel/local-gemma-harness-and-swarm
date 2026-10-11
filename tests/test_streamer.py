import io
import sys
from harness_tui import TerminalMarkdownStreamer, render_diff_preview

def test_bullet_formatting_preserves_bold():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        # Feed bullet with bold text
        streamer.feed("- **Bold Item** with description\n")
        streamer.flush()
        output = buffer.getvalue()
        # Verify bold asterisks are NOT stripped
        assert "**Bold Item**" in output
        assert "•" in output
    finally:
        sys.stdout = old_stdout

def test_nested_bullet_preserves_indentation():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        streamer.feed("    - Sub-bullet item\n")
        streamer.flush()
        output = buffer.getvalue()
        assert "    " in output  # 4-space indent preserved
        assert "•" in output
        assert "Sub-bullet item" in output
    finally:
        sys.stdout = old_stdout

def test_code_fence_formatting():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        streamer.feed("```python\nx = 1\n```\n")
        streamer.flush()
        output = buffer.getvalue()
        assert "┌── python" in output
        assert "│" in output
        assert "└──" in output
    finally:
        sys.stdout = old_stdout

def test_render_diff_preview_replacement():
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        tool_args = {
            "TargetFile": "test_module.py",
            "TargetContent": "def old():\n    return 1",
            "ReplacementContent": "def new():\n    return 2",
        }
        render_diff_preview("replace_file_content", tool_args)
        output = buffer.getvalue()
        assert "Proposed Diff: test_module.py" in output
        assert "-def old():" in output
        assert "+def new():" in output
    finally:
        sys.stdout = old_stdout

def test_render_diff_preview_new_file():
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        tool_args = {
            "TargetFile": "nonexistent_new_file.py",
            "CodeContent": "print('hello world')",
            "Append": False,
        }
        render_diff_preview("write_to_file", tool_args)
        output = buffer.getvalue()
        assert "Creating new file: nonexistent_new_file.py" in output
        assert "print('hello world')" in output
    finally:
        sys.stdout = old_stdout

def test_thought_block_multiline_formatting():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        streamer.feed("<thought>\n")
        streamer.feed("Step 1: Inspect problem\n")
        streamer.feed("Step 2: Generate solution\n")
        streamer.feed("</thought>\nHere is the answer.\n")
        streamer.flush()
        output = buffer.getvalue()
        assert "┌── 💭 Thinking Process" in output
        assert "│" in output
        assert "Step 1: Inspect problem" in output
        assert "Step 2: Generate solution" in output
        assert "└── 💭 Thought for" in output
        assert "tokens" in output
        assert streamer.thought_tokens >= 2
        assert "Here is the answer." in output
    finally:
        sys.stdout = old_stdout

def test_thought_inline_formatting():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        streamer.feed("<thought>Analyzing requirements...</thought>\nDirect output.\n")
        streamer.flush()
        output = buffer.getvalue()
        assert "┌── 💭 Thinking Process" in output
        assert "Analyzing requirements..." in output
        assert "└── 💭 Thought for" in output
        assert "Direct output." in output
    finally:
        sys.stdout = old_stdout

def test_thought_unclosed_flush():
    streamer = TerminalMarkdownStreamer()
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        streamer.feed("<thought>\nThinking without end tag")
        streamer.flush()
        output = buffer.getvalue()
        assert "┌── 💭 Thinking Process" in output
        assert "Thinking without end tag" in output
        assert "└── 💭 Thought for" in output
    finally:
        sys.stdout = old_stdout
