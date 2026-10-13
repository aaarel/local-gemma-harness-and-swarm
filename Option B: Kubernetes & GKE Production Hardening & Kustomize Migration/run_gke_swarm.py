#!/usr/bin/env python3
"""
run_gke_swarm.py — Kubernetes / GKE Production Hardening & Kustomize Migration Swarm

Option B Use Case: Kubernetes & GKE Production Hardening & Kustomize Migration
Triad Architecture:
1. Cloud Gemini via Antigravity CLI (agy): GKE Platform Architect (Zero API keys needed)
2. Local Gemma 4 26B (Metal GPU): Coder & Runbook Author (Kustomize multi-environment overlays)
3. Local Gemma 4 26B (Fresh Context): Independent GKE Security Auditor (CIS GKE Benchmark & PSS Restricted)
4. Iteration Loop: Coder patches any issues identified by the Auditor
5. Local Verification: YAML syntax validation & kustomize build
"""

import argparse
import asyncio
import os
import sys
import time

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rich.console import Console
from rich.panel import Panel

from session_manager import SessionManager
from swarm import (
    HybridSwarm,
    GKE_PLANNER_PROMPT,
    GKE_WORKER_PROMPT,
    GKE_SECURITY_AUDITOR_PROMPT,
)

DEFAULT_INPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "input_workload")
)
DEFAULT_WORKSPACE = os.path.abspath(
    os.path.join(REPO_ROOT, "workspaces", "gke-production-hardening")
)
DEFAULT_MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")

DEFAULT_OBJECTIVE = (
    "Analyze the unhardened development workload in the input directory and migrate it into "
    "a production-ready, security-hardened Kustomize multi-environment structure for Google Kubernetes Engine (GKE). "
    "Strict requirements: "
    "1. Enforce Kubernetes Pod Security Standards: restricted (runAsNonRoot: true, runAsUser: 10001, "
    "   readOnlyRootFilesystem: true, allowPrivilegeEscalation: false, capabilities: drop: ['ALL'], seccomp RuntimeDefault). "
    "2. Configure GKE Workload Identity Federation (annotate ServiceAccount with GCP IAM Service Account). "
    "3. Define HorizontalPodAutoscaler (HPA v2) targeting 70% CPU and PodDisruptionBudget (PDB minAvailable: 1). "
    "4. Implement strict NetworkPolicy ingress and egress rules restricting traffic to required ports only. "
    "5. Define structured liveness, readiness, and startup HTTP probes. "
    "6. Layout: base/ (deployment, service, configmap, hpa, pdb, networkpolicy, kustomization.yaml), "
    "   overlays/dev/ (replica patch, dev env), overlays/prod/ (3 replicas, multi-zone anti-affinity, prod env). "
    "7. Author RUNBOOK.md detailing cluster prerequisites, namespace creation, kubectl apply -k overlays/prod, and rollback."
)

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="GKE Production Hardening Swarm Runner")
    parser.add_argument(
        "--objective", "-o",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="GKE hardening objective and workload requirements",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=str,
        default=DEFAULT_WORKSPACE,
        help="Target workspace directory where Kustomize overlays will be generated",
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=str,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing unhardened development workload (docker-compose, deployment)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=DEFAULT_MODEL_PATH,
        help="Path to local Gemma 4 LiteRT model checkpoint",
    )
    parser.add_argument(
        "--cloud-backend",
        choices=["agy", "genai"],
        default="agy",
        help="Cloud Gemini backend: 'agy' (Antigravity CLI, zero API keys) or 'genai' (API key)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    workspace_path = os.path.abspath(args.workspace)
    input_dir = os.path.abspath(args.input_dir)
    model_path = os.path.abspath(os.path.expanduser(args.model))

    if not os.path.exists(model_path):
        console.print(f"[bold red][!] Local Gemma model not found at: {model_path}[/bold red]")
        sys.exit(1)

    os.makedirs(workspace_path, exist_ok=True)
    session_mgr = SessionManager(workspace_path)
    session = session_mgr.create_session(
        title="GKE Production Hardening & Kustomize Migration",
        model="hybrid-gemini-gemma-gke",
    )

    # Ingest context from input directory if present
    input_context = ""
    if os.path.exists(input_dir):
        files_found = []
        for root, _, files in os.walk(input_dir):
            for f in files:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, input_dir)
                try:
                    with open(p, "r", encoding="utf-8") as inf:
                        files_found.append(f"--- File: {rel} ---\n{inf.read()}\n")
                except Exception:
                    pass
        if files_found:
            input_context = "\nInput Unhardened Workload Files:\n" + "\n".join(files_found)

    full_objective = f"{args.objective}\n{input_context}"

    banner = (
        f"[bold cyan]Use Case:[/bold cyan] Option B — Kubernetes & GKE Production Hardening & Kustomize Migration\n"
        f"[bold cyan]Input Workload:[/bold cyan] {input_dir}\n"
        f"[bold cyan]Cloud Planner:[/bold cyan] Gemini via Antigravity CLI ([bold green]No API Key Needed[/bold green])\n"
        f"[bold cyan]Local Worker:[/bold cyan] Gemma 4 26B on Apple Silicon Metal GPU\n"
        f"[bold cyan]Security Auditor:[/bold cyan] Gemma 4 26B (Fresh Context, CIS GKE Benchmark & PSS Restricted)\n"
        f"[bold cyan]Target Workspace:[/bold cyan] {workspace_path}\n"
        f"[bold cyan]Session ID:[/bold cyan] {session.session_id}\n\n"
        f"[bold yellow]Objective:[/bold yellow]\n{args.objective}"
    )
    console.print(Panel(banner, title="[bold yellow]☸️ GKE Production Hardening Swarm — Option B[/bold yellow]", border_style="yellow"))

    swarm = HybridSwarm(
        model_path=model_path,
        workspace_path=workspace_path,
        cloud_backend=args.cloud_backend,
        planner_prompt=GKE_PLANNER_PROMPT,
        worker_prompt=GKE_WORKER_PROMPT,
        auditor_prompt=GKE_SECURITY_AUDITOR_PROMPT,
        session=session,
        title="GKE hardening (Kustomize)",
        worker_task="Generate the complete Kustomize structure (base/, overlays/dev/, overlays/prod/) and RUNBOOK.md now.",
        audit_task="Review the generated Kustomize manifests and RUNBOOK.md against the CIS GKE Benchmark and Pod Security Standards (Restricted).",
    )

    t_start = time.time()
    try:
        current_stage = None
        async for stage, token in swarm.execute_swarm(full_objective):
            if stage != current_stage:
                current_stage = stage
            sys.stdout.write(token)
            sys.stdout.flush()

        t_total = time.time() - t_start
        console.print(f"\n\n[bold green]✓ GKE Production Hardening Swarm completed in {t_total:.1f}s![/bold green]")
        console.print(f"[dim]Generated Kustomize Package: {workspace_path}[/dim]")
        console.print(f"[dim]Session Transcript: {session.transcript_path}[/dim]\n")

    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚡ Swarm execution aborted by user.[/bold yellow]\n")


if __name__ == "__main__":
    asyncio.run(main())
