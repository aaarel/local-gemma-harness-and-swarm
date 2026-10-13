#!/usr/bin/env python3
"""
run_hybrid.py — Hybrid Cloud + On-Device AI Swarm Runner for GCP Infrastructure

Option A Use Case: Production-Grade GCP Terraform Module Scaffolding & Validation
- Cloud Gemini: Cloud Solutions Architect (One-shot planning & HCL specification)
- Local Gemma 4 26B: Apple Silicon Metal implementation worker (offline tool execution)
- Local Terraform: Automated verification (init & validate)
"""

import argparse
import asyncio
import os
import sys
import time

# Ensure repository root is on sys.path so harness modules resolve cleanly
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rich.console import Console
from rich.panel import Panel

from session_manager import SessionManager
from swarm import HybridSwarm

DEFAULT_OBJECTIVE = (
    "Scaffold a production-ready, security-hardened Google Cloud Platform (GCP) Terraform module "
    "for a Private Cloud Run v2 service connected to a Cloud SQL PostgreSQL instance. "
    "Strict requirements: "
    "1. Cloud SQL must be private IP only (RFC 1918), no public IP, require SSL, with IAM db authentication enabled. "
    "2. Cloud Run v2 must use Direct VPC egress or a Serverless VPC connector with ALL_TRAFFIC egress and internal ingress. "
    "3. Dedicated custom App Service Account with least-privilege roles (roles/cloudsql.client, Secret Manager accessor). "
    "4. Output files: versions.tf (hashicorp/google ~> 6.0), variables.tf with validation, main.tf, iam.tf, and outputs.tf."
)

DEFAULT_MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")
DEFAULT_WORKSPACE = os.path.abspath(os.path.join(REPO_ROOT, "workspaces", "terraform-gcp-secure-cloudrun"))

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Hybrid Cloud + Local Swarm Runner (Gemini + Gemma)")
    parser.add_argument(
        "--objective", "-o",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="Infrastructure objective for the swarm to execute",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=str,
        default=DEFAULT_WORKSPACE,
        help="Target directory where Gemma will generate and validate code",
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
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Google Gemini model for cloud planning (default: gemini-2.5-flash)",
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
    session = session_mgr.create_session(title="Hybrid Swarm: GCP Cloud Run & Cloud SQL", model="hybrid-gemini-gemma")

    banner = (
        f"[bold cyan]Use Case:[/bold cyan] Option A — Production-Grade GCP Terraform Module Scaffolding\n"
        f"[bold cyan]Swarm Mode:[/bold cyan] Hybrid (Cloud Gemini Planner + Local Gemma Worker)\n"
        f"[bold cyan]Cloud Planner:[/bold cyan] {args.cloud_backend.upper()} ({args.gemini_model})\n"
        f"[bold cyan]Local Worker:[/bold cyan] Gemma 4 26B on Apple Silicon Metal GPU\n"
        f"[bold cyan]Target Workspace:[/bold cyan] {workspace_path}\n"
        f"[bold cyan]Session ID:[/bold cyan] {session.session_id}\n\n"
        f"[bold yellow]Objective:[/bold yellow]\n{args.objective}"
    )
    console.print(Panel(banner, title="[bold yellow]Hybrid AI Swarm — Option A[/bold yellow]", border_style="yellow"))

    swarm = HybridSwarm(
        model_path=model_path,
        workspace_path=workspace_path,
        cloud_backend=args.cloud_backend,
        gemini_model=args.gemini_model,
        session=session,
        title="Private Cloud Run + Cloud SQL module",
        worker_task=(
            "Write the Terraform module files (versions.tf, variables.tf, main.tf, iam.tf, outputs.tf) "
            "in the target workspace now."
        ),
        audit_task=(
            "Review the generated Terraform module for security issues: private IP only, SSL required, "
            "least-privilege service account, internal ingress and VPC egress."
        ),
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
        console.print(f"\n\n[bold green]✓ Hybrid Swarm completed successfully in {t_total:.1f}s![/bold green]")
        console.print(f"[dim]Artifacts generated in: {workspace_path}[/dim]")
        console.print(f"[dim]Session log saved: {session.transcript_path}[/dim]\n")

    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚡ Hybrid Swarm aborted by user.[/bold yellow]\n")


if __name__ == "__main__":
    asyncio.run(main())
