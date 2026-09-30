import os
import json
import tempfile
import pytest
from pathlib import Path
from session_manager import SessionManager, Session, safe_code_block

def test_safe_code_block_collision():
    # Prompt with 3 backticks should use 4 backticks
    prompt_with_code = "Here is some code:\n```python\nprint('hello')\n```"
    block = safe_code_block(prompt_with_code)
    assert block.startswith("````text")
    assert block.endswith("````")

    # Prompt with 4 backticks should use 5 backticks
    prompt_with_nested = "Outer:\n````\ninner\n````"
    block5 = safe_code_block(prompt_with_nested)
    assert block5.startswith("`````text")
    assert block5.endswith("`````")

def test_session_lifecycle_and_atomic_writes():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(tmpdir)
        session = sm.create_session(title="Unit Test Session", model="gemma4-26b")
        
        # Verify creation and atomic metadata
        assert session.metadata_file.exists()
        with open(session.metadata_file, "r") as f:
            meta = json.load(f)
        assert meta["title"] == "Unit Test Session"
        assert meta["turn_count"] == 0

        # Verify events.jsonl
        assert session.events_file.exists()
        with open(session.events_file, "r") as f:
            events = [json.loads(line) for line in f]
        assert len(events) >= 1
        assert events[0]["event"] == "session_created"

        # Append turn
        session.append_turn("What is Python?", "Python is a language.", duration_sec=1.5)
        assert session.turn_count == 1
        assert session.transcript_file.exists()

        # Log tool call
        session.log_tool_call("run_command", {"CommandLine": "ls"}, 0.25, allowed=True)
        with open(session.events_file, "r") as f:
            events = [json.loads(line) for line in f]
        tool_events = [e for e in events if e.get("event") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_name"] == "run_command"
        assert tool_events[0]["duration_sec"] == 0.25

        # Interrupted turn
        session.append_interrupted_turn("Another prompt", "Partial...", duration_sec=0.8)
        assert session.turn_count == 2
        transcript_text = session.transcript_file.read_text()
        assert "Interrupted" in transcript_text

        # Numeric and title resolution
        res1 = sm.resolve_session("1")
        assert res1 is not None
        assert res1.session_id == session.session_id

        res_title = sm.resolve_session("Unit Test")
        assert res_title is not None
        assert res_title.session_id == session.session_id

        # Deletion
        assert sm.delete_session("1") is True
        assert sm.get_session(session.session_id) is None
