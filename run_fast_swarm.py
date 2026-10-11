#!/usr/bin/env python3
"""
run_fast_swarm.py — Cloud Foundation Fabric FAST Landing Zone Swarm Runner

Triad Architecture:
1. Cloud Gemini via Antigravity CLI (agy): Cloud Solutions Architect & FAST Planner (Zero API keys needed)
2. Local Gemma 4 26B (Metal GPU): Coder & Runbook Author
3. Local Gemma 4 26B (Fresh Context): Independent CIS Benchmark Security Auditor
4. Iteration Loop: Coder patches any issues identified by the Auditor
5. Local Verification: terraform validate across all stages
"""

import argparse
import asyncio
import os
import sys
import time

from rich.console import Console
from rich.panel import Panel

from session_manager import SessionManager
from swarm import HybridSwarm

DEFAULT_OBJECTIVE = (
    "Plan and generate an off-the-shelf, production-grade Google Cloud Foundation Fabric FAST "
    "landing zone for a small customer (Acme Corp, domain: acme-corp.com, prefix: fast, region: europe-west1). "
    "Required deliverables: "
    "1. 0-bootstrap stage: Automation project, Terraform state GCS bucket (uniform access, versioning), CI/CD SAs, billing alert budget, org audit log sink. "
    "2. 1-resman stage: Resource hierarchy ('Platform' and 'Workloads' folders), essential CIS GCP Org Policies (disable default VPC, disable external SA keys, enforce uniform bucket access), and group IAM bindings. "
    "3. 2-networking stage: Single Shared VPC with prod (10.0.1.0/24) and dev (10.0.2.0/24) subnets, Cloud NAT, Private Google Access, and secure firewall rules. "
    "4. 3-project-factory stage: Tenant workload project definition attached to Shared VPC with Workload Identity. "
    "5. RUNBOOK.md: Comprehensive operational deployment guide for the infra engineer covering prerequisites, Day-0 bootstrap execution, state migration, stage execution order, and Day-2 operations. "
    "Note: Do not deploy to live GCP; generate the complete Terraform codebase and runbook locally."
)

DEFAULT_MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")
DEFAULT_WORKSPACE = os.path.abspath("workspaces/fast-landing-zone")

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Fabric FAST Landing Zone Hybrid Swarm Runner")
    parser.add_argument(
        "--objective", "-o",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="Landing zone objective and customer requirements",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=str,
        default=DEFAULT_WORKSPACE,
        help="Target workspace directory where FAST stages will be generated",
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
    model_path = os.path.abspath(os.path.expanduser(args.model))

    if not os.path.exists(model_path):
        console.print(f"[bold red][!] Local Gemma model not found at: {model_path}[/bold red]")
        sys.exit(1)

    os.makedirs(workspace_path, exist_ok=True)
    session_mgr = SessionManager(workspace_path)
    session = session_mgr.create_session(
        title="Fabric FAST Landing Zone (Small Customer)",
        model="hybrid-gemini-gemma-fast",
    )

    banner = (
        f"[bold cyan]Architecture:[/bold cyan] Google Cloud Foundation Fabric FAST (Small Customer)\n"
        f"[bold cyan]Cloud Planner:[/bold cyan] Gemini via Antigravity CLI ([bold green]No API Key Needed[/bold green])\n"
        f"[bold cyan]Local Worker:[/bold cyan] Gemma 4 26B on Apple Silicon Metal GPU\n"
        f"[bold cyan]Security Auditor:[/bold cyan] Gemma 4 26B (Fresh Context, CIS GCP Benchmark v3.0 Level 1)\n"
        f"[bold cyan]Target Workspace:[/bold cyan] {workspace_path}\n"
        f"[bold cyan]Session ID:[/bold cyan] {session.session_id}\n\n"
        f"[bold yellow]Objective:[/bold yellow]\n{args.objective}"
    )
    console.print(Panel(banner, title="[bold yellow]🚀 Fabric FAST Hybrid Swarm[/bold yellow]", border_style="yellow"))

    swarm = HybridSwarm(
        model_path=model_path,
        workspace_path=workspace_path,
        cloud_backend=args.cloud_backend,
        session=session,
    )

    t_start = time.time()
    try:
        current_stage = None
        async for stage, token in swarm.execute_swarm(args.objective):
            if stage != current_stage:
                current_stage = stage
            sys.stdout.write(token)
            sys.stdout.flush()

        t_total = time.time() - t_start
        console.print(f"\n\n[bold green]✓ Fabric FAST Swarm completed in {t_total:.1f}s![/bold green]")
        console.print(f"[dim]Generated Landing Zone: {workspace_path}[/dim]")
        console.print(f"[dim]Session Transcript: {session.transcript_path}[/dim]\n")

    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚡ Swarm execution aborted by user.[/bold yellow]\n")


if __name__ == "__main__":
    asyncio.run(main())
