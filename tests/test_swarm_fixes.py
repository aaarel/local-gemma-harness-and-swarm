"""Tests for the swarm safety fixes: agy timeout, tool restrictions, verdict parsing, per-use-case tasks."""

import asyncio
import os
import stat

import pytest

from google.antigravity import types
from swarm import FAST_AUDIT_TASK, FAST_WORKER_TASK, HybridSwarm, audit_requests_revision


def _swarm(tmp_path, **kwargs):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    return HybridSwarm(model_path="/fake/path", workspace_path=str(ws), cloud_backend="agy", **kwargs)


@pytest.mark.parametrize("text, expected", [
    ("### Report\n- Status: PASS\n- Findings: none", False),
    ("- Status: REVISION NEEDED\n- Critical: open SSH", True),
    ("- Status: [REVISION NEEDED]", True),
    ("Status: PASS — no revision needed", False),
    ("- Status: PASS or REVISION NEEDED (write exactly one)\n- Status: PASS", False),
    ("**Status:** REVISION NEEDED", True),
    ("Everything looks fine. [PASS]", False),
    ("Verdict: [REVISION NEEDED]", True),
])
def test_audit_verdict_parsing(text, expected):
    assert audit_requests_revision(text) is expected


def test_worker_has_no_shell_and_reviewer_only_reads(tmp_path):
    swarm = _swarm(tmp_path)
    worker = swarm._create_worker_config()
    assert types.BuiltinTools.RUN_COMMAND not in worker.capabilities.enabled_tools
    assert types.BuiltinTools.CREATE_FILE in worker.capabilities.enabled_tools
    reviewer = swarm._create_reviewer_config()
    assert reviewer.capabilities.enabled_tools == [types.BuiltinTools.VIEW_FILE]


def test_tasks_default_and_override(tmp_path):
    assert _swarm(tmp_path).worker_task == FAST_WORKER_TASK
    assert _swarm(tmp_path).audit_task == FAST_AUDIT_TASK
    gke = _swarm(tmp_path, worker_task="Generate Kustomize", audit_task="Audit GKE", title="GKE")
    assert (gke.worker_task, gke.audit_task, gke.title) == ("Generate Kustomize", "Audit GKE", "GKE")


def test_explicit_backend_choice_is_kept(tmp_path):
    ws = tmp_path / "ws2"
    ws.mkdir()
    swarm = HybridSwarm(model_path="/fake", workspace_path=str(ws), cloud_backend="genai", gemini_api_key="k")
    assert swarm.cloud_backend == "genai"


def _fake_agy(tmp_path, body):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    agy = bin_dir / "agy"
    agy.write_text("#!/bin/sh\n" + body)
    agy.chmod(agy.stat().st_mode | stat.S_IEXEC)
    return bin_dir


async def _collect(gen):
    return [chunk async for chunk in gen]


def test_agy_plan_runs_in_empty_dir_and_asks_for_text_only(tmp_path, monkeypatch):
    bin_dir = _fake_agy(tmp_path, 'echo "cwd=$(pwd)"\necho "prompt=$2" | tr "\\n" " "\necho\n')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    swarm = _swarm(tmp_path, agy_timeout=10)
    out = "".join(asyncio.run(_collect(swarm._execute_cloud_plan_via_agy("Build a landing zone"))))
    assert "agy-plan-" in out                      # ran from a fresh temp dir
    assert "Do not call any tools" in out          # text-only instruction appended
    assert "Build a landing zone" in out


def test_agy_plan_times_out_and_is_killed(tmp_path, monkeypatch):
    bin_dir = _fake_agy(tmp_path, "echo starting\nsleep 30\necho never\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    swarm = _swarm(tmp_path, agy_timeout=1)
    with pytest.raises(RuntimeError, match="did not finish within 1s"):
        asyncio.run(_collect(swarm._execute_cloud_plan_via_agy("x")))


def test_agy_plan_reports_failures(tmp_path, monkeypatch):
    bin_dir = _fake_agy(tmp_path, "echo boom >&2\nexit 3\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    swarm = _swarm(tmp_path, agy_timeout=10)
    with pytest.raises(RuntimeError, match="code 3: boom"):
        asyncio.run(_collect(swarm._execute_cloud_plan_via_agy("x")))


def test_tool_timing_summary(tmp_path):
    swarm = _swarm(tmp_path)
    swarm.tool_call_times = [101.0, 104.0, 110.0]
    line = swarm._tool_timing_summary(100.0)
    assert "Tool calls: 3" in line and "first 1.0s" in line and "last 6.0s" in line
