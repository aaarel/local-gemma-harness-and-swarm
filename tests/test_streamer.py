import io
import sys
from harness_tui import TerminalMarkdownStreamer

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
