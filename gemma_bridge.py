#!/usr/bin/env python3
"""Start, check, query and stop the local Gemma server (stdlib only, any python3).

Used by the `local-gemma-bridge` skill in AGY, by fast_slice.py, and by hand:

  python3 gemma_bridge.py status      # exit 0 = ready, 1 = not running, 2 = loading or failed
  python3 gemma_bridge.py start       # start in the background if needed, wait until ready
  python3 gemma_bridge.py ask "Explain what this rule allows" --file rules.yaml
  python3 gemma_bridge.py ask "Review this module" --file main.tf --out review.md
                                      # --out: the answer stays in a local file; only a summary is printed
  python3 gemma_bridge.py stop

Environment: GEMMA_BRIDGE_URL (default http://127.0.0.1:8765), GEMMA_MODEL_PATH, GEMMA_BACKEND.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = os.environ.get("GEMMA_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
LOG_DIR = os.path.join(REPO, "logs")
SERVER_LOG = os.path.join(LOG_DIR, "gemma_server.log")
REQUEST_LOG = os.path.join(LOG_DIR, "gemma_requests.jsonl")
PID_FILE = os.path.join(LOG_DIR, "gemma_server.pid")
MAX_FILE_BYTES = 200_000

# localhost only: never send these requests through a corporate HTTP proxy
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BridgeError(RuntimeError):
    pass


def _call(method: str, path: str, body: Optional[Dict[str, Any]] = None, *, url: str = DEFAULT_URL,
          timeout: float = 10.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    return _OPENER.open(req, timeout=timeout)


def health(url: str = DEFAULT_URL, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Returns the server's health JSON, or None if nothing is listening."""
    try:
        with _call("GET", "/health", url=url, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # 503 while loading or failed still has a JSON body
        try:
            return json.loads(e.read())
        except Exception:  # pylint: disable=broad-exception-caught
            return {"status": f"http-{e.code}"}
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _tail(path: str, lines: int = 25) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return "(no log)"


def _server_python() -> str:
    venv = os.path.join(REPO, ".venv", "bin", "python")
    return venv if os.path.exists(venv) else sys.executable


def spawn_server(url: str = DEFAULT_URL, model: Optional[str] = None, backend: Optional[str] = None,
                 extra_args: Optional[List[str]] = None) -> subprocess.Popen:
    """Starts gemma_server.py detached from this process (it keeps running after we exit)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    port = urllib.parse.urlparse(url).port or 8765
    cmd = [_server_python(), os.path.join(REPO, "gemma_server.py"), "--port", str(port),
           "--request-log", REQUEST_LOG]
    if model:
        cmd += ["--model", model]
    if backend:
        cmd += ["--backend", backend]
    cmd += extra_args or []
    with open(SERVER_LOG, "ab") as log_file:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=log_file, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    return proc


def wait_until_ready(url: str = DEFAULT_URL, timeout: float = 300.0, proc: Optional[subprocess.Popen] = None,
                     quiet: bool = False) -> Dict[str, Any]:
    t0 = time.time()
    last_note = -10.0
    while True:
        h = health(url)
        status = h.get("status") if h else None
        if status == "ready":
            return h  # type: ignore[return-value]
        if status == "error":
            raise BridgeError(f"model failed to load: {h.get('error')}\nLog: {SERVER_LOG}")  # type: ignore[union-attr]
        if proc is not None and proc.poll() is not None:
            raise BridgeError(f"server exited with code {proc.returncode}. Last log lines:\n{_tail(SERVER_LOG)}")
        elapsed = time.time() - t0
        if elapsed > timeout:
            raise BridgeError(f"not ready after {timeout:.0f}s (status: {status}). Log: {SERVER_LOG}")
        if not quiet and elapsed - last_note >= 5:
            print(f"… {status or 'starting'} ({elapsed:.0f}s)", file=sys.stderr, flush=True)
            last_note = elapsed
        time.sleep(1.0)


def ensure_running(url: str = DEFAULT_URL, model: Optional[str] = None, backend: Optional[str] = None,
                   timeout: float = 300.0, extra_args: Optional[List[str]] = None,
                   quiet: bool = False) -> Dict[str, Any]:
    """Returns the health JSON once the model is ready, starting the server if needed."""
    h = health(url)
    proc = None
    if h is None:
        if not quiet:
            print(f"Starting the local Gemma server (log: {os.path.relpath(SERVER_LOG)}). "
                  "The first start compiles GPU shaders and can take 1-2 minutes.", file=sys.stderr, flush=True)
        proc = spawn_server(url, model or os.environ.get("GEMMA_MODEL_PATH"),
                            backend or os.environ.get("GEMMA_BACKEND"), extra_args)
    elif h.get("status") == "ready":
        return h
    t0 = time.time()
    h = wait_until_ready(url, timeout, proc, quiet)
    if not quiet:
        print(f"✓ Gemma ready ({h.get('model')}, {h.get('backend')}; model load {h.get('load_seconds')}s, "
              f"waited {time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
    return h


def chat(messages: List[Dict[str, str]], *, url: str = DEFAULT_URL, max_tokens: int = 2048,
         thinking: bool = False, temperature: Optional[float] = None, seed: Optional[int] = None,
         top_k: Optional[int] = None, top_p: Optional[float] = None,
         on_delta: Optional[Callable[[str, str], None]] = None, timeout: float = 900.0) -> Dict[str, Any]:
    """Streams one chat completion. Returns {"content", "reasoning", "timing"}.

    With temperature > 0 and no seed, the server picks a random seed (see timing["seed"]).
    """
    body: Dict[str, Any] = {"messages": messages, "stream": True, "max_tokens": max_tokens, "thinking": thinking}
    for key, value in (("temperature", temperature), ("seed", seed), ("top_k", top_k), ("top_p", top_p)):
        if value is not None:
            body[key] = value
    content: List[str] = []
    reasoning: List[str] = []
    timing: Dict[str, Any] = {}
    try:
        with _call("POST", "/v1/chat/completions", body, url=url, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                obj = json.loads(data)
                delta = ((obj.get("choices") or [{}])[0].get("delta")) or {}
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
                    if on_delta:
                        on_delta("reasoning", delta["reasoning_content"])
                if delta.get("content"):
                    content.append(delta["content"])
                    if on_delta:
                        on_delta("content", delta["content"])
                if obj.get("x_timing"):
                    timing = obj["x_timing"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise BridgeError(f"server returned HTTP {e.code}: {detail[:500]}") from e
    except (urllib.error.URLError, OSError) as e:
        raise BridgeError(f"cannot reach the Gemma server at {url}: {e}. Run: python3 gemma_bridge.py start") from e
    return {"content": "".join(content), "reasoning": "".join(reasoning), "timing": timing}


def format_timing(t: Dict[str, Any]) -> str:
    if not t:
        return "(no timing)"
    parts = [f"TTFT {t.get('ttft_s')}s", f"total {t.get('total_s')}s",
             f"{t.get('chunks')} chunks (~tokens) at {t.get('chunks_per_s')}/s"]
    if t.get("reasoning_chunks"):
        parts.append(f"{t['reasoning_chunks']} thinking")
    if (t.get("queue_s") or 0) > 0.5:
        parts.append(f"queued {t['queue_s']}s")
    return " | ".join(parts)


def build_user_message(prompt: str, files: List[str]) -> str:
    parts = [prompt.strip()]
    for path in files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(MAX_FILE_BYTES + 1)
        if len(text) > MAX_FILE_BYTES:
            text = text[:MAX_FILE_BYTES] + "\n[... truncated ...]"
        parts.append(f"\n\n### File: {path}\n```\n{text}\n```")
    return "".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_status(args: argparse.Namespace) -> int:
    h = health(args.url)
    if h is None:
        print(f"not running (nothing listening at {args.url}). Start it with: python3 gemma_bridge.py start")
        return 1
    print(json.dumps(h, indent=2))
    return 0 if h.get("status") == "ready" else 2


def _cmd_start(args: argparse.Namespace) -> int:
    try:
        h = ensure_running(args.url, args.model, args.backend, args.timeout)
    except BridgeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(json.dumps({k: h.get(k) for k in ("status", "model", "backend", "load_seconds", "pid")}))
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    try:
        if not args.no_start:
            ensure_running(args.url, args.model, args.backend, args.timeout)
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        messages.append({"role": "user", "content": build_user_message(" ".join(args.prompt), args.file or [])})
        streaming = not args.out and not args.json
        last_kind = [""]

        def on_delta(kind: str, text: str) -> None:
            if kind == "content" or args.show_thinking:
                if kind == "content" and last_kind[0] == "reasoning":
                    sys.stdout.write("\n\n")
                last_kind[0] = kind
                sys.stdout.write(text if kind == "content" else f"\033[2m{text}\033[0m")
                sys.stdout.flush()

        result = chat(messages, url=args.url, max_tokens=args.max_tokens, thinking=args.think,
                      temperature=args.temperature, seed=args.seed,
                      on_delta=on_delta if streaming else None)
    except (BridgeError, OSError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    elif args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result["content"])
        print(f"✓ Gemma's answer was written to {args.out} ({len(result['content'])} chars). "
              f"{format_timing(result['timing'])}")
    else:
        print()
        print(f"⏱ {format_timing(result['timing'])}", file=sys.stderr)
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    try:
        with _call("POST", "/shutdown", {}, url=args.url, timeout=5):
            pass
        print("✓ stop requested")
    except (urllib.error.URLError, OSError):
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, encoding="utf-8") as f:
                    os.kill(int(f.read().strip()), signal.SIGTERM)
                print("✓ sent SIGTERM to the server process")
            except (OSError, ValueError):
                print("not running")
        else:
            print("not running")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Control and query the local Gemma server.")
    p.add_argument("--url", default=DEFAULT_URL)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Print health; exit 0 ready, 1 not running, 2 loading/failed")
    for name in ("start", "ask"):
        sp = sub.add_parser(name)
        sp.add_argument("--model", default=None, help="Path to the .litertlm file (default: GEMMA_MODEL_PATH or Gemma 4 26B)")
        sp.add_argument("--backend", choices=["gpu", "cpu"], default=None)
        sp.add_argument("--timeout", type=float, default=300.0, help="Seconds to wait for the model to load")
        if name == "ask":
            sp.add_argument("prompt", nargs="+", help="The instruction for Gemma (make it self-contained)")
            sp.add_argument("--file", action="append", help="Attach a local file (repeatable); read locally")
            sp.add_argument("--system", default=None, help="System prompt")
            sp.add_argument("--out", default=None, help="Write the answer to this file and print only a summary")
            sp.add_argument("--think", action="store_true", help="Let Gemma think first (slower)")
            sp.add_argument("--show-thinking", action="store_true", help="Print the thinking text too")
            sp.add_argument("--max-tokens", type=int, default=2048)
            sp.add_argument("--temperature", type=float, default=None)
            sp.add_argument("--seed", type=int, default=None, help="Sampling seed for reproducibility")
            sp.add_argument("--no-start", action="store_true", help="Fail instead of starting the server")
            sp.add_argument("--json", action="store_true", help="Print the full result as JSON")
    sub.add_parser("stop", help="Stop the server")
    args = p.parse_args(argv)
    return {"status": _cmd_status, "start": _cmd_start, "ask": _cmd_ask, "stop": _cmd_stop}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
