#!/usr/bin/env python3
"""Persistent local Gemma server with a health check (the AGY bridge backend).

AGY can't select a local model, so this keeps Gemma loaded in unified memory
and exposes a small OpenAI-compatible HTTP API on 127.0.0.1. Any client can use
it: curl, the `local-gemma-bridge` skill (AGY), gemma_bridge.py, fast_slice.py,
or an OpenAI SDK pointed at http://127.0.0.1:8765/v1.

It calls LiteRT-LM directly: no Antigravity SDK, no Go harness, no gRPC.
One generation runs at a time; other requests wait for their turn.

Endpoints:
  GET  /health               200 when ready, 503 while loading or failed (JSON body)
  GET  /v1/models            OpenAI-style model list
  POST /v1/chat/completions  OpenAI-style chat, streaming or not.
                             Extra request field: "thinking": true|false (default false).
                             Sampling: "temperature", "top_k", "top_p", "seed". With
                             temperature > 0 and no seed, a random seed is used.
                             Extra response field: "x_timing" (queue, TTFT, totals, chunks, seed).
                             One chunk is roughly one token in LiteRT-LM 0.17.
  POST /shutdown             Stop the server.
  GET  /                     Minimal chat page (disable with --no-ui).

Usage:
  .venv/bin/python gemma_server.py                 # Gemma 4 26B on the Metal GPU, port 8765
  .venv/bin/python gemma_server.py --backend cpu   # CPU instead of GPU
  .venv/bin/python gemma_server.py --fake          # no model, canned replies (tests)
Most people start it through `python3 gemma_bridge.py start` instead.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

DEFAULT_MODEL = os.path.expanduser(
    os.environ.get("GEMMA_MODEL_PATH", "~/.litert-lm/models/gemma4-26b/model.litertlm")
)
DEFAULT_PORT = int(os.environ.get("GEMMA_BRIDGE_PORT", "8765"))
DEFAULT_BACKEND = os.environ.get("GEMMA_BACKEND", "gpu" if sys.platform == "darwin" else "cpu")
DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/gemma-bridge/litert")
FAKE_REPLY_SEPARATOR = "---8<---"

Event = Tuple[str, str]  # ("content" | "reasoning", text)


def log(msg: str) -> None:
    print(f"[gemma-server {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _text_of(content: Any) -> str:
    """OpenAI content can be a string or a list of parts; keep the text parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text"):
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return str(content)


def normalize_messages(raw: Any) -> List[Dict[str, str]]:
    """Validates OpenAI-style messages and returns [{"role", "content"}] with text content."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("'messages' must be a non-empty list")
    out = []
    for i, m in enumerate(raw):
        if not isinstance(m, dict):
            raise ValueError(f"messages[{i}] must be an object")
        role = m.get("role")
        if role == "developer":
            role = "system"
        if role == "model":
            role = "assistant"
        if role not in ("system", "user", "assistant"):
            raise ValueError(f"messages[{i}]: unsupported role {role!r} (system, user, assistant)")
        out.append({"role": role, "content": _text_of(m.get("content"))})
    if out[-1]["role"] != "user":
        raise ValueError("the last message must have role 'user'")
    return out


def build_sampling(body: Dict[str, Any], rng: Optional[random.Random] = None) -> Optional[Dict[str, Any]]:
    """Reads temperature / seed / top_k / top_p from a request body for LiteRT's SamplerConfig.

    LiteRT-LM uses a fixed seed when none is given, so temperature alone gives the
    same text on every call. When temperature > 0 and the caller didn't send a seed,
    pick a random one. The seed is reported in x_timing so a run can be replayed.
    Returns None when nothing is set (LiteRT defaults).
    """
    sampling: Dict[str, Any] = {}
    for key, cast in (("temperature", float), ("top_p", float), ("top_k", int), ("seed", int)):
        value = body.get(key)
        if value is not None:
            sampling[key] = cast(value)
    if sampling.get("temperature", 0.0) > 0:
        if "top_k" not in sampling and "top_p" not in sampling:
            sampling["top_k"] = 40
        if "seed" not in sampling:
            sampling["seed"] = (rng or random).randrange(1, 2**31 - 1)
    return sampling or None


def _split_chunk(chunk: Any) -> Iterator[Event]:
    """Turns one LiteRT-LM stream chunk into (kind, text) events.

    Thinking arrives in separate fields ("reasoning_content", "channels.thought"),
    not in the text content. (The Antigravity SDK's own loopback server only
    forwards text, so it drops these.)
    """
    if not isinstance(chunk, dict):
        if chunk:
            yield ("content", str(chunk))
        return
    reasoning = chunk.get("reasoning_content")
    if not reasoning and isinstance(chunk.get("channels"), dict):
        reasoning = chunk["channels"].get("thought")
    if reasoning:
        yield ("reasoning", str(reasoning))
    content = chunk.get("content")
    if isinstance(content, str):
        if content:
            yield ("content", content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                yield ("content", str(item["text"]))


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class LiteRTBackend:
    """Gemma through litert_lm.Engine (needs the litert-lm package and a .litertlm file)."""

    name = "litert"

    def __init__(self, model_path: str, backend: str, max_num_tokens: int, cache_dir: Optional[str]):
        import litert_lm  # imported here so --fake works without litert-lm

        self.lm = litert_lm
        try:
            litert_lm.set_min_log_severity(int(litert_lm.LogSeverity.ERROR))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        hardware = litert_lm.Backend.GPU() if backend == "gpu" else litert_lm.Backend.CPU()
        kwargs: Dict[str, Any] = {"backend": hardware, "max_num_tokens": max_num_tokens, "cache_dir": cache_dir}
        try:
            # Same option the Antigravity SDK uses: bigger contexts with less memory.
            self._engine = litert_lm.Engine(model_path, use_ringbuffers_local_attention=True, **kwargs)
        except TypeError:
            self._engine = litert_lm.Engine(model_path, **kwargs)
        self._ctx = self._engine.__enter__()

    def _message(self, m: Dict[str, str]) -> Any:
        lm = self.lm
        if m["role"] == "system":
            return lm.Message.system(m["content"])
        if m["role"] == "user":
            return lm.Message.user(m["content"])
        contents = lm.Contents.of(m["content"]) if m["content"] else lm.Contents.empty()
        return lm.Message.model(contents=contents)

    def stream(self, messages: List[Dict[str, str]], max_output_tokens: int, thinking: bool,
               thinking_budget: int, sampling: Optional[Dict[str, Any]]) -> Iterator[Event]:
        lm = self.lm
        converted = [self._message(m) for m in messages]
        context, prompt = converted[:-1], converted[-1]
        if thinking:
            thinking_config = lm.ThinkingConfig(enable_thinking=True, thinking_token_budget=thinking_budget)
        else:
            thinking_config = lm.ThinkingConfig(enable_thinking=False)
        # Only pass the keys that were set; LiteRT keeps its own defaults for the rest.
        sampler = lm.SamplerConfig(**sampling) if sampling else None
        with self._ctx.create_conversation(
            messages=context,
            automatic_tool_calling=False,
            max_output_tokens=max_output_tokens,
            thinking_config=thinking_config,
            sampler_config=sampler,
        ) as conv:
            for chunk in conv.send_message_async(prompt):
                yield from _split_chunk(chunk)

    def close(self) -> None:
        try:
            self._engine.__exit__(None, None, None)
        except Exception:  # pylint: disable=broad-exception-caught
            pass


class FakeBackend:
    """No model. Replies with scripted text (tests) or echoes the prompt."""

    name = "fake"

    def __init__(self, replies: Optional[List[str]] = None, delay: float = 0.002):
        self.replies = list(replies or [])
        self.delay = delay
        self.calls = 0
        self.last_sampling: Optional[Dict[str, Any]] = None

    def stream(self, messages: List[Dict[str, str]], max_output_tokens: int, thinking: bool,
               thinking_budget: int, sampling: Optional[Dict[str, Any]]) -> Iterator[Event]:
        self.calls += 1
        self.last_sampling = sampling
        if thinking:
            yield ("reasoning", "Thinking about the request... ")
        if self.replies:
            text = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        else:
            text = f"[fake gemma] You said: {messages[-1]['content'][:200]}"
        for piece in re.findall(r"\S+\s*|\s+", text):
            if self.delay:
                time.sleep(self.delay)
            yield ("content", piece)

    def close(self) -> None:
        pass


def read_fake_replies(path: Optional[str]) -> List[str]:
    if not path:
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [r.strip("\n") for r in f.read().split(FAKE_REPLY_SEPARATOR) if r.strip()]


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class GemmaServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], backend_factory: Callable[[], Any], *, model_label: str,
                 backend_label: str, max_output_tokens: int = 4096, thinking_budget: int = 1024,
                 ui: bool = True, request_log: Optional[str] = None):
        super().__init__(address, GemmaHandler)
        self.backend_factory = backend_factory
        self.backend: Any = None
        self.model_label = model_label
        self.backend_label = backend_label
        self.max_output_tokens = max_output_tokens
        self.thinking_budget = thinking_budget
        self.ui = ui
        self.request_log = request_log
        self.engine_lock = threading.Lock()  # LiteRT-LM serves one generation at a time
        self.state_lock = threading.Lock()
        self.status = "starting"
        self.error: Optional[str] = None
        self.started_at = time.time()
        self.load_seconds: Optional[float] = None
        self.requests_served = 0
        self.in_flight = 0
        self.last_timing: Optional[Dict[str, Any]] = None

    # -- model lifecycle ---------------------------------------------------
    def load_in_background(self) -> None:
        threading.Thread(target=self._load, name="gemma-loader", daemon=True).start()

    def _load(self) -> None:
        self.status = "loading"
        t0 = time.time()
        log(f"loading {self.model_label} on {self.backend_label} ...")
        try:
            self.backend = self.backend_factory()
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.status = "error"
            self.error = f"{type(e).__name__}: {e}"
            log(f"model load FAILED: {self.error}")
            return
        self.load_seconds = round(time.time() - t0, 2)
        self.status = "ready"
        log(f"ready in {self.load_seconds}s")

    def close_backend(self) -> None:
        if self.backend is not None:
            self.backend.close()
            self.backend = None

    def health(self) -> Dict[str, Any]:
        with self.state_lock:
            return {
                "status": self.status,
                "model": self.model_label,
                "backend": self.backend_label,
                "load_seconds": self.load_seconds,
                "uptime_s": round(time.time() - self.started_at, 1),
                "requests_served": self.requests_served,
                "in_flight": self.in_flight,
                "last_request": self.last_timing,
                "error": self.error,
                "pid": os.getpid(),
            }

    # -- generation ----------------------------------------------------------
    def generate(self, messages: List[Dict[str, str]], max_tokens: int, thinking: bool,
                 sampling: Optional[Dict[str, Any]] = None) -> Iterator[Event]:
        """Yields events; the final timing dict is stored in self.last_timing."""
        received = time.time()
        with self.state_lock:
            self.in_flight += 1
        timing: Dict[str, Any] = {}
        try:
            with self.engine_lock:
                start = time.time()
                first = first_content = None
                n_reasoning = n_content = 0
                for kind, text in self.backend.stream(messages, max_tokens, thinking, self.thinking_budget, sampling):
                    now = time.time()
                    if first is None:
                        first = now
                    if kind == "reasoning":
                        n_reasoning += 1
                    else:
                        n_content += 1
                        if first_content is None:
                            first_content = now
                    yield (kind, text)
                end = time.time()
            chunks = n_reasoning + n_content
            decode_s = max(1e-3, end - (first or start))
            timing = {
                "queue_s": round(start - received, 3),
                "ttft_s": round((first or end) - start, 3),
                "ttft_content_s": round((first_content or end) - start, 3),
                "total_s": round(end - start, 3),
                "reasoning_chunks": n_reasoning,
                "content_chunks": n_content,
                "chunks": chunks,
                "chunks_per_s": round(chunks / decode_s, 1) if chunks else 0.0,
                "thinking": thinking,
                "temperature": (sampling or {}).get("temperature"),
                "seed": (sampling or {}).get("seed"),
            }
        finally:
            with self.state_lock:
                self.in_flight -= 1
                if timing:
                    self.requests_served += 1
                    self.last_timing = timing
        if timing:
            log(f"request {self.requests_served}: {timing['chunks']} chunks "
                f"({timing['reasoning_chunks']} thinking) in {timing['total_s']}s, "
                f"TTFT {timing['ttft_s']}s, {timing['chunks_per_s']} chunks/s")
            if self.request_log:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(self.request_log)), exist_ok=True)
                    with open(self.request_log, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **timing}) + "\n")
                except OSError:
                    pass


class GemmaHandler(BaseHTTPRequestHandler):
    server: GemmaServer
    server_version = "gemma-server/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        pass  # keep the log for model events only

    def address_string(self) -> str:
        return self.client_address[0]  # no reverse DNS lookups (offline-friendly)

    # -- helpers ---------------------------------------------------------------
    def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, message: str, **extra: Any) -> None:
        self._send_json(code, {"error": {"message": message, "code": code}, **extra})

    def _path(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    # -- routes ----------------------------------------------------------------
    def do_GET(self) -> None:  # pylint: disable=invalid-name
        path = self._path()
        if path == "/health":
            h = self.server.health()
            self._send_json(200 if h["status"] == "ready" else 503, h)
        elif path == "/v1/models":
            self._send_json(200, {"object": "list", "data": [{
                "id": self.server.model_label, "object": "model",
                "created": int(self.server.started_at), "owned_by": "local"}]})
        elif path in ("/", "/index.html") and self.server.ui:
            body = UI_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._error(404, f"not found: {path}")

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        path = self._path()
        if path == "/shutdown":
            self._send_json(200, {"status": "shutting down"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path != "/v1/chat/completions":
            self._error(404, f"not found: {path}")
            return
        if self.server.status != "ready":
            self._error(503, f"model not ready (status: {self.server.status})", health=self.server.health())
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            messages = normalize_messages(body.get("messages"))
        except (ValueError, json.JSONDecodeError) as e:
            self._error(400, f"bad request: {e}")
            return
        max_tokens = int(body.get("max_tokens") or body.get("max_completion_tokens") or self.server.max_output_tokens)
        thinking = bool(body.get("thinking", False))
        if str(body.get("reasoning_effort", "")).lower() in ("low", "medium", "high"):
            thinking = True
        try:
            sampling = build_sampling(body)
        except (TypeError, ValueError) as e:
            self._error(400, f"bad request: {e}")
            return
        events = self.server.generate(messages, max_tokens, thinking, sampling)
        try:
            if body.get("stream"):
                self._stream(events)
            else:
                self._complete(events)
        except (BrokenPipeError, ConnectionResetError):
            log("client disconnected before the answer was complete")
        except Exception as e:  # pylint: disable=broad-exception-caught
            log(f"generation failed: {type(e).__name__}: {e}")
            try:
                self._error(500, f"generation failed: {type(e).__name__}: {e}")
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    def _complete(self, events: Iterator[Event]) -> None:
        content: List[str] = []
        reasoning: List[str] = []
        for kind, text in events:
            (reasoning if kind == "reasoning" else content).append(text)
        message: Dict[str, Any] = {"role": "assistant", "content": "".join(content)}
        if reasoning:
            message["reasoning_content"] = "".join(reasoning)
        self._send_json(200, {
            "id": "chatcmpl-" + uuid.uuid4().hex[:12],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.server.model_label,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "x_timing": self.server.last_timing,
        })

    def _stream(self, events: Iterator[Event]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()  # HTTP/1.0: the connection closes when the stream ends
        cid = "chatcmpl-" + uuid.uuid4().hex[:12]
        created = int(time.time())

        def send(delta: Dict[str, Any], finish: Optional[str] = None, **extra: Any) -> None:
            chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                     "model": self.server.model_label,
                     "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extra}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.flush()

        send({"role": "assistant"})
        for kind, text in events:
            send({"reasoning_content": text} if kind == "reasoning" else {"content": text})
        send({}, "stop", x_timing=self.server.last_timing)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


UI_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Local Gemma</title>
<style>
body{font-family:ui-monospace,Menlo,monospace;max-width:880px;margin:2em auto;padding:0 1em;background:#111;color:#ddd}
#log{white-space:pre-wrap;border:1px solid #333;border-radius:6px;padding:1em;min-height:14em;max-height:65vh;overflow:auto}
.you{color:#7fd1ff}.think{color:#a08cc8;font-style:italic}.meta{color:#888;font-size:.85em}
textarea{width:100%;height:5em;margin-top:.8em;background:#1b1b1b;color:#eee;border:1px solid #333;border-radius:6px;padding:.5em}
button{margin-top:.4em;padding:.35em 1.2em}
</style></head><body>
<h3>Local Gemma <span id="st" class="meta"></span></h3>
<div id="log"></div>
<textarea id="q" placeholder="Ask local Gemma (Ctrl/Cmd+Enter to send)"></textarea>
<label class="meta"><input type="checkbox" id="th"> thinking</label> <button id="go">Send</button>
<script>
const log=document.getElementById('log'),q=document.getElementById('q'),st=document.getElementById('st');
const history=[];
async function health(){try{const r=await fetch('/health');const j=await r.json();
 st.textContent='· '+j.status+' · '+j.model+' · '+j.backend;}catch(e){st.textContent='· server down';}}
health();setInterval(health,3000);
function add(cls,text){const s=document.createElement('span');s.className=cls;s.textContent=text;log.appendChild(s);return s;}
async function send(){
 const text=q.value.trim();if(!text)return;q.value='';
 add('you','\\n> '+text+'\\n');history.push({role:'user',content:text});
 const think=add('think',''),ans=add('','');let content='',timing=null;
 const r=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({messages:history,stream:true,thinking:document.getElementById('th').checked})});
 if(!r.ok){ans.textContent='[error '+r.status+'] '+await r.text();history.pop();return;}
 const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
 while(true){const {value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});
  let i;while((i=buf.indexOf('\\n\\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+2);
   if(!line.startsWith('data:'))continue;const data=line.slice(5).trim();if(data==='[DONE]')continue;
   const j=JSON.parse(data);const d=(j.choices&&j.choices[0]&&j.choices[0].delta)||{};
   if(d.reasoning_content)think.textContent+=d.reasoning_content;
   if(d.content){content+=d.content;ans.textContent=content;}
   if(j.x_timing)timing=j.x_timing;log.scrollTop=log.scrollHeight;}}
 history.push({role:'assistant',content});
 if(timing)add('meta','\\n[TTFT '+timing.ttft_s+'s · total '+timing.total_s+'s · '+timing.chunks+' chunks · '+timing.chunks_per_s+'/s]\\n');
 log.scrollTop=log.scrollHeight;}
document.getElementById('go').onclick=send;
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey))send();});
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Persistent local Gemma server (OpenAI-compatible) with /health.")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Path to the .litertlm checkpoint")
    p.add_argument("--host", default="127.0.0.1", help="Bind address (keep it on localhost)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--backend", choices=["gpu", "cpu"], default=DEFAULT_BACKEND)
    p.add_argument("--max-num-tokens", type=int, default=16384,
                   help="KV-cache size in tokens (the Antigravity SDK uses 65536; smaller uses less memory)")
    p.add_argument("--max-output-tokens", type=int, default=4096, help="Default max tokens per answer")
    p.add_argument("--thinking-budget", type=int, default=1024, help="Thinking tokens when a request asks for thinking")
    p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Compilation/weight cache directory")
    p.add_argument("--request-log", default=None, help="Append per-request timing as JSON lines to this file")
    p.add_argument("--no-ui", action="store_true", help="Don't serve the chat page at /")
    p.add_argument("--fake", action="store_true", help="No model: scripted/echo replies (for tests)")
    p.add_argument("--fake-replies", default=None, help=f"File with fake replies separated by '{FAKE_REPLY_SEPARATOR}'")
    p.add_argument("--fake-load-seconds", type=float, default=0.0, help="Simulated model load time with --fake")
    return p.parse_args(argv)


def build_server(args: argparse.Namespace) -> GemmaServer:
    if args.fake:
        replies = read_fake_replies(args.fake_replies)

        def factory() -> Any:
            time.sleep(args.fake_load_seconds)
            return FakeBackend(replies)

        model_label, backend_label = "fake-gemma", "fake"
    else:
        model_path = os.path.abspath(os.path.expanduser(args.model))
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"model not found: {model_path} (set --model or GEMMA_MODEL_PATH)")

        def factory() -> Any:
            return LiteRTBackend(model_path, args.backend, args.max_num_tokens, args.cache_dir)

        parent = os.path.basename(os.path.dirname(model_path))
        model_label = parent if os.path.basename(model_path) == "model.litertlm" and parent else os.path.basename(model_path)
        backend_label = args.backend
    return GemmaServer((args.host, args.port), factory, model_label=model_label, backend_label=backend_label,
                       max_output_tokens=args.max_output_tokens, thinking_budget=args.thinking_budget,
                       ui=not args.no_ui, request_log=args.request_log)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        server = build_server(args)
    except FileNotFoundError as e:
        log(str(e))
        return 2
    except OSError as e:
        log(f"cannot listen on {args.host}:{args.port}: {e}. Is a server already running? Try: python3 gemma_bridge.py status")
        return 3
    host, port = server.server_address[:2]
    log(f"listening on http://{host}:{port} (model: {server.model_label}, backend: {server.backend_label}, pid {os.getpid()})")
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    # Serve HTTP from a background thread so /health answers "loading" right away, and load the
    # engine on the main thread (the same split the Antigravity SDK uses for its LiteRT server).
    http_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25},
                                   name="gemma-http", daemon=True)
    http_thread.start()
    try:
        server._load()  # pylint: disable=protected-access
        while http_thread.is_alive():
            http_thread.join(0.5)
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        server.server_close()
        server.close_backend()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
