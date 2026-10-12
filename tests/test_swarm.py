import asyncio
import os
import shutil
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from google.antigravity import types
from swarm import (
    LocalSwarm,
    HybridSwarm,
    PLANNER_PROMPT,
    WORKER_PROMPT,
    HYBRID_WORKER_PROMPT,
    SECURITY_AUDITOR_PROMPT,
    GKE_PLANNER_PROMPT,
    GKE_WORKER_PROMPT,
    GKE_SECURITY_AUDITOR_PROMPT,
)


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


def test_hybrid_swarm_configs_and_backends(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. GenAI backend without API Key raises ValueError
    swarm_genai_no_key = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="genai",
        gemini_api_key="",
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
        asyncio.run(swarm_genai_no_key._execute_cloud_plan_via_genai("Build infra").__anext__())

    # 2. Worker config uses CustomSystemInstructions with HYBRID_WORKER_PROMPT
    swarm_agy = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="agy",
    )
    worker_cfg = swarm_agy._create_worker_config()
    assert worker_cfg.model_path == "/fake/path"
    assert worker_cfg.workspaces == [str(workspace)]
    assert isinstance(worker_cfg.system_instructions, types.CustomSystemInstructions)
    assert worker_cfg.system_instructions.text == HYBRID_WORKER_PROMPT

    # 3. Reviewer config uses CustomSystemInstructions with SECURITY_AUDITOR_PROMPT
    reviewer_cfg = swarm_agy._create_reviewer_config()
    assert reviewer_cfg.model_path == "/fake/path"
    assert reviewer_cfg.workspaces == [str(workspace)]
    assert isinstance(reviewer_cfg.system_instructions, types.CustomSystemInstructions)
    assert reviewer_cfg.system_instructions.text == SECURITY_AUDITOR_PROMPT


def test_hybrid_swarm_gke_prompts_and_overrides(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    swarm_gke = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="agy",
        planner_prompt=GKE_PLANNER_PROMPT,
        worker_prompt=GKE_WORKER_PROMPT,
        auditor_prompt=GKE_SECURITY_AUDITOR_PROMPT,
    )
    assert swarm_gke.planner_prompt == GKE_PLANNER_PROMPT

    worker_cfg = swarm_gke._create_worker_config()
    assert worker_cfg.system_instructions.text == GKE_WORKER_PROMPT

    reviewer_cfg = swarm_gke._create_reviewer_config()
    assert reviewer_cfg.system_instructions.text == GKE_SECURITY_AUDITOR_PROMPT


@pytest.mark.anyio
async def test_hybrid_swarm_verification_no_files(tmp_path):
    workspace = tmp_path / "empty_ws"
    workspace.mkdir()

    swarm = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="agy",
    )
    result = await swarm.execute_verification()
    assert "No .tf or .yaml files detected" in result


@pytest.mark.anyio
async def test_hybrid_swarm_verification_multi_stage_terraform(tmp_path):
    workspace = tmp_path / "fast_ws"
    workspace.mkdir()

    # Create two stages with minimal valid terraform files
    stage0 = workspace / "0-bootstrap"
    stage0.mkdir()
    (stage0 / "versions.tf").write_text("""
terraform {
  required_version = ">= 1.0"
}
""")

    stage1 = workspace / "1-resman"
    stage1.mkdir()
    (stage1 / "versions.tf").write_text("""
terraform {
  required_version = ">= 1.0"
}
""")

    swarm = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="agy",
    )
    result = await swarm.execute_verification()
    if shutil.which("terraform"):
        assert "Running Terraform validation" in result
        assert "0-bootstrap" in result
        assert "1-resman" in result
    else:
        assert "terraform binary not found" in result


@pytest.mark.anyio
async def test_hybrid_swarm_verification_kubernetes_yaml(tmp_path):
    workspace = tmp_path / "k8s_ws"
    workspace.mkdir()

    # Create minimal valid kubernetes YAML manifest
    (workspace / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
    spec:
      containers:
        - name: app
          image: nginx:latest
""")

    swarm = HybridSwarm(
        model_path="/fake/path",
        workspace_path=str(workspace),
        cloud_backend="agy",
    )
    result = await swarm.execute_verification()
    assert "YAML manifests are syntactically valid" in result
