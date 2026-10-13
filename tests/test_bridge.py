"""Tests for gemma_server.py and gemma_bridge.py with the fake backend (no model needed)."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

import gemma_bridge
import gemma_server


def _start(backend_factory, **kwargs):
    server = gemma_server.GemmaServer(("127.0.0.1", 0), backend_factory, model_label="test-gemma",
                                      backend_label="fake", **kwargs)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, url


@pytest.fixture
def ready_server():
    server, url = _start(lambda: gemma_server.FakeBackend(["Hello from fake Gemma."]))
    server.load_in_background()
    gemma_bridge.wait_until_ready(url, timeout=10, quiet=True)
    yield server, url
    server.shutdown()
    server.server_close()


def test_health_reports_loading_then_ready():
    gate = threading.Event()

    def slow_factory():
        gate.wait(5)
        return gemma_server.FakeBackend()

    server, url = _start(slow_factory)
    try:
        server.load_in_background()
        time.sleep(0.1)
        h = gemma_bridge.health(url)
        assert h["status"] == "loading"
        # chat is refused with 503 while the model loads
        with pytest.raises(gemma_bridge.BridgeError, match="HTTP 503"):
            gemma_bridge.chat([{"role": "user", "content": "hi"}], url=url)
        gate.set()
        h = gemma_bridge.wait_until_ready(url, timeout=10, quiet=True)
        assert h["status"] == "ready"
        assert h["load_seconds"] is not None
    finally:
        server.shutdown()
        server.server_close()


def test_health_reports_load_errors():
    def broken_factory():
        raise FileNotFoundError("no such model")

    server, url = _start(broken_factory)
    try:
        server.load_in_background()
        with pytest.raises(gemma_bridge.BridgeError, match="no such model"):
            gemma_bridge.wait_until_ready(url, timeout=5, quiet=True)
    finally:
        server.shutdown()
        server.server_close()


def test_health_is_none_when_nothing_listens():
    assert gemma_bridge.health("http://127.0.0.1:9", timeout=0.5) is None


def test_streaming_chat_returns_content_and_timing(ready_server):
    server, url = ready_server
    deltas = []
    result = gemma_bridge.chat([{"role": "user", "content": "hi"}], url=url,
                               on_delta=lambda kind, text: deltas.append(kind))
    assert result["content"] == "Hello from fake Gemma."
    assert result["reasoning"] == ""
    assert result["timing"]["content_chunks"] > 0
    assert set(deltas) == {"content"}
    assert server.health()["requests_served"] == 1


def test_thinking_comes_back_as_reasoning(ready_server):
    _, url = ready_server
    result = gemma_bridge.chat([{"role": "user", "content": "hi"}], url=url, thinking=True)
    assert result["reasoning"].startswith("Thinking")
    assert result["content"] == "Hello from fake Gemma."
    assert result["timing"]["reasoning_chunks"] > 0
    assert result["timing"]["thinking"] is True


def test_non_streaming_openai_shape(ready_server):
    _, url = ready_server
    body = json.dumps({"messages": [{"role": "system", "content": "be brief"},
                                    {"role": "user", "content": [{"type": "text", "text": "hi"}]}]}).encode()
    req = urllib.request.Request(url + "/v1/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello from fake Gemma."
    assert "x_timing" in data


def test_bad_requests_get_400(ready_server):
    _, url = ready_server
    for messages in ([], [{"role": "assistant", "content": "x"}], [{"role": "tool", "content": "x"}]):
        req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps({"messages": messages}).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=10)
        assert err.value.code == 400


def test_models_and_ui(ready_server):
    _, url = ready_server
    with urllib.request.urlopen(url + "/v1/models", timeout=5) as r:
        assert json.loads(r.read())["data"][0]["id"] == "test-gemma"
    with urllib.request.urlopen(url + "/", timeout=5) as r:
        assert b"Local Gemma" in r.read()


def test_shutdown_endpoint():
    server, url = _start(lambda: gemma_server.FakeBackend())
    server.load_in_background()
    gemma_bridge.wait_until_ready(url, timeout=10, quiet=True)
    assert gemma_bridge.main(["--url", url, "stop"]) == 0
    time.sleep(0.5)
    assert gemma_bridge.health(url, timeout=0.5) is None
    server.server_close()


def test_status_cli_exit_codes(ready_server, capsys):
    _, url = ready_server
    assert gemma_bridge.main(["--url", url, "status"]) == 0
    assert gemma_bridge.main(["--url", "http://127.0.0.1:9", "status"]) == 1


def test_ask_cli_writes_out_file(ready_server, tmp_path, capsys):
    _, url = ready_server
    src = tmp_path / "rules.yaml"
    src.write_text("ingress: {}\n")
    out = tmp_path / "answer.md"
    rc = gemma_bridge.main(["--url", url, "ask", "Review this", "--file", str(src), "--out", str(out), "--no-start"])
    assert rc == 0
    assert out.read_text() == "Hello from fake Gemma."
    printed = capsys.readouterr().out
    assert "written to" in printed and "Hello from fake Gemma." not in printed


def test_build_user_message_attaches_files(tmp_path):
    f = tmp_path / "main.tf"
    f.write_text('resource "x" "y" {}\n')
    msg = gemma_bridge.build_user_message("Review it", [str(f)])
    assert msg.startswith("Review it")
    assert "### File:" in msg and 'resource "x" "y"' in msg


def test_split_chunk_handles_litert_shapes():
    text = {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]}
    thought = {"role": "assistant", "channels": {"thought": "hmm"}, "reasoning_content": "hmm"}
    assert list(gemma_server._split_chunk(text)) == [("content", "Hi")]
    assert list(gemma_server._split_chunk(thought)) == [("reasoning", "hmm")]


def test_fake_replies_file(tmp_path):
    f = tmp_path / "replies.txt"
    f.write_text(f"first\n{gemma_server.FAKE_REPLY_SEPARATOR}\nsecond\n")
    assert gemma_server.read_fake_replies(str(f)) == ["first", "second"]
