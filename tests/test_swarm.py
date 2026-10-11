import asyncio
import os
import shutil
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from google.antigravity import types
from swarm import LocalSwarm, HybridSwarm, PLANNER_PROMPT, WORKER_PROMPT, HYBRID_WORKER_PROMPT


def test_local_swarm_config_creation(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    swarm = LocalSwarm(model_path="/fake/path", workspace_path=str(workspace))

    # Read-only config (Planner / Reviewer)
    ro_config = swarm._create_role_config(PLANNER_PROMPT, write_allowed=False)
    assert ro_config.model_path == "/fake/path"
    assert ro_config.workspaces == [str(workspace)]
    assert isinstance(ro_config.system_instructions, types.CustomSystemInstructions)
    assert ro_config.system_instructions.text == PLANNER_PROMPT

    # Write-allowed config (Worker)
    rw_config = swarm._create_role_config(WORKER_PROMPT, write_allowed=True)
    assert isinstance(rw_config.system_instructions, types.CustomSystemInstructions)
    assert rw_config.system_instructions.text == WORKER_PROMPT


def test_hybrid_swarm_config_and_api_key_guard(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Missing API Key raises ValueError
    swarm_no_key = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        gemini_api_key="",
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
        asyncio.run(swarm_no_key.execute_cloud_plan("Build infra").__anext__())

    # 2. Worker config uses CustomSystemInstructions with HYBRID_WORKER_PROMPT
    swarm_with_key = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        gemini_api_key="test_key_123",
        gemini_model="gemini-2.5-flash",
    )
    worker_cfg = swarm_with_key._create_worker_config()
    assert worker_cfg.model_path == "/fake/path"
    assert worker_cfg.workspaces == [str(workspace)]
    assert isinstance(worker_cfg.system_instructions, types.CustomSystemInstructions)
    assert worker_cfg.system_instructions.text == HYBRID_WORKER_PROMPT


@pytest.mark.anyio
async def test_hybrid_swarm_verification_no_tf(tmp_path):
    workspace = tmp_path / "empty_ws"
    workspace.mkdir()

    swarm = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        gemini_api_key="test_key",
    )
    result = await swarm.execute_verification()
    assert "No .tf files detected" in result


@pytest.mark.anyio
async def test_hybrid_swarm_verification_with_terraform(tmp_path):
    workspace = tmp_path / "tf_ws"
    workspace.mkdir()

    # Create a minimal valid terraform file
    (workspace / "versions.tf").write_text("""
terraform {
  required_version = ">= 1.0"
}
""")

    swarm = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        gemini_api_key="test_key",
    )
    result = await swarm.execute_verification()
    # If terraform is installed on machine, it should run init and validate
    if shutil.which("terraform"):
        assert "Running Terraform validation" in result
        assert "terraform validate passed" in result or "terraform init" in result
    else:
        assert "terraform binary not found" in result
