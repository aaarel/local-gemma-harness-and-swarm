import asyncio
import os
import shutil
import subprocess
import sys
import time
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

from google.antigravity import Agent, LiteRTAgentConfig, types
from google.antigravity.hooks import policy

from session_manager import Session

PLANNER_PROMPT = """You are the PLANNER in a local multi-agent software engineering swarm.
Your job is to analyze the user's objective, inspect the workspace, and generate a concise, actionable, step-by-step implementation plan.
Focus on:
1. Exact files to inspect or modify.
2. Architecture and design decisions.
3. Verification and test criteria.
Do not write code directly; output only the concrete execution plan for the Worker."""

WORKER_PROMPT = """You are the WORKER / CODER in a local multi-agent software engineering swarm.
Your job is to execute the implementation plan produced by the Planner.
You write clean, modular, production-ready code, edit existing files, and execute commands to verify the environment.
Follow the plan strictly and report what changes were made."""

REVIEWER_PROMPT = """You are the REVIEWER in a local multi-agent software engineering swarm.
Your job is to critically review the Worker's implementation against the original objective and plan.
1. Inspect the modified files.
2. Run test commands or lint checks if appropriate.
3. Conclude with either:
   - PASS: if the implementation meets the requirements and tests pass.
   - REVISION NEEDED: with specific constructive items to fix."""

HYBRID_PLANNER_PROMPT = """You are the LEAD CLOUD SOLUTIONS ARCHITECT and INFRASTRUCTURE PLANNER in a hybrid AI development swarm.
Your partner is an on-device AI coding agent (Gemma 4 running locally on Apple Silicon Metal) that has direct file writing and command execution capabilities.

Your task is to analyze the user's infrastructure/software objective and emit a structured, production-grade Execution Blueprint.

Strict guidelines for your plan:
1. ARCHITECTURE & SPECIFICATIONS: State exact services, versions, and security guardrails (e.g. CIS GCP Benchmark, least-privilege IAM, private networking, SSL enforcement).
2. FILE-BY-FILE BLUEPRINT: Detail every single file to create or modify (e.g. versions.tf, variables.tf, main.tf, iam.tf, outputs.tf). Provide the exact HCL resource block structures, parameter names, and variable definitions so the local coder has an unambiguous implementation specification.
3. VERIFICATION COMMANDS: Specify the exact local CLI commands to execute (e.g., `terraform init -backend=false`, `terraform validate`, `pytest`) to verify syntax, correctness, and policies.

Be precise, structured, and authoritative. Do not ask clarifying questions; make sound enterprise-grade architectural choices."""

HYBRID_WORKER_PROMPT = """You are the ON-DEVICE IMPLEMENTATION WORKER in a hybrid AI software engineering swarm.
You run 100% locally on Apple Silicon Metal with full access to Antigravity tools (write_to_file, replace_file_content, run_command, view_file).

Your task:
1. Review the Execution Blueprint provided by the Cloud Architect (Gemini).
2. Execute the plan by creating all required files using `write_to_file`.
3. Ensure every configuration is complete, syntactically valid, and includes all necessary arguments and resource blocks.
4. Execute the verification commands using `run_command` (e.g. `terraform init -backend=false` and `terraform validate`).
5. If any validation errors occur, fix them immediately using `replace_file_content` or `write_to_file` until verification succeeds.
6. Report a clean summary of files created and verification outcomes."""


class LocalSwarm:
    """
    Multi-role agent swarm executing against a single loaded LiteRT model on Apple Silicon.
    Roles take turns sequentially (Planner -> Worker -> Reviewer) without duplicating model weights in memory.
    """
    def __init__(self, model_path: str, workspace_path: str, session: Optional[Session] = None):
        self.model_path = model_path
        self.workspace_path = workspace_path
        self.session = session

    def _create_role_config(self, system_instructions: str, write_allowed: bool = False) -> LiteRTAgentConfig:
        return LiteRTAgentConfig(
            model_path=self.model_path,
            workspaces=[self.workspace_path],
            policies=[policy.allow_all()] if write_allowed else [policy.allow(types.BuiltinTools.VIEW_FILE)],
            system_instructions=types.CustomSystemInstructions(text=system_instructions),
            save_dir=str(self.session.conversation_dir) if self.session else None,
            app_data_dir=str(self.session.app_data_dir) if self.session else None,
        )

    async def execute_swarm(self, objective: str) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Executes the 3-stage sequential local swarm pipeline:
        Stage 1: Planner
        Stage 2: Worker
        Stage 3: Reviewer
        Yields (stage_name, token) for live streaming.
        """
        # Stage 1: Planning
        yield ("PLANNER", f"\n[bold yellow]═══ Stage 1: Swarm Planner (Local Gemma) ═══[/bold yellow]\n")
        plan_tokens = []
        plan_config = self._create_role_config(PLANNER_PROMPT, write_allowed=False)
        async with Agent(plan_config) as planner:
            resp = await planner.chat(f"Create an implementation plan for this objective:\n{objective}")
            async for token in resp:
                plan_tokens.append(token)
                yield ("PLANNER", token)
        plan_text = "".join(plan_tokens)

        # Stage 2: Worker Execution
        yield ("WORKER", f"\n\n[bold green]═══ Stage 2: Swarm Worker / Builder (Local Gemma) ═══[/bold green]\n")
        worker_tokens = []
        worker_config = self._create_role_config(WORKER_PROMPT, write_allowed=True)
        async with Agent(worker_config) as worker:
            worker_prompt = f"Objective:\n{objective}\n\nPlan to execute:\n{plan_text}\n\nProceed with implementing this plan now."
            resp = await worker.chat(worker_prompt)
            async for token in resp:
                worker_tokens.append(token)
                yield ("WORKER", token)
        worker_text = "".join(worker_tokens)

        # Stage 3: Review & Verification
        yield ("REVIEWER", f"\n\n[bold cyan]═══ Stage 3: Swarm Reviewer / QA (Local Gemma) ═══[/bold cyan]\n")
        reviewer_tokens = []
        reviewer_config = self._create_role_config(REVIEWER_PROMPT, write_allowed=False)
        async with Agent(reviewer_config) as reviewer:
            reviewer_prompt = f"Objective:\n{objective}\n\nPlan:\n{plan_text}\n\nWorker output:\n{worker_text}\n\nReview the implementation and deliver your verdict."
            resp = await reviewer.chat(reviewer_prompt)
            async for token in resp:
                reviewer_tokens.append(token)
                yield ("REVIEWER", token)
        reviewer_text = "".join(reviewer_tokens)

        if self.session:
            full_swarm_summary = f"### Local Swarm Objective: {objective}\n\n#### Plan:\n{plan_text}\n\n#### Implementation:\n{worker_text}\n\n#### Review:\n{reviewer_text}"
            self.session.append_turn(f"/swarm {objective}", full_swarm_summary)


class HybridSwarm:
    """
    Hybrid Cloud + On-Device Agent Swarm:
    Stage 1: Cloud Gemini (Architect / Planner) via google-genai SDK.
    Stage 2: Local Gemma 4 26B (Worker / Coder) via LiteRT on Apple Silicon Metal.
    Stage 3: Automated CLI Verification & Quality Audit (terraform validate, tests, etc.).
    """
    def __init__(
        self,
        model_path: str,
        workspace_path: str,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        session: Optional[Session] = None,
    ):
        self.model_path = model_path
        self.workspace_path = workspace_path
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.session = session

    def _create_worker_config(self) -> LiteRTAgentConfig:
        return LiteRTAgentConfig(
            model_path=self.model_path,
            workspaces=[self.workspace_path],
            policies=[policy.allow_all()],
            system_instructions=types.CustomSystemInstructions(text=HYBRID_WORKER_PROMPT),
            save_dir=str(self.session.conversation_dir) if self.session else None,
            app_data_dir=str(self.session.app_data_dir) if self.session else None,
        )

    async def execute_cloud_plan(self, objective: str) -> AsyncGenerator[str, None]:
        """
        Streams architectural plan from Cloud Gemini using google-genai SDK.
        """
        if not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide it in .env or via export GEMINI_API_KEY=your_key.\n"
                "Get your key at: https://aistudio.google.com/"
            )

        client = genai.Client(api_key=self.gemini_api_key)
        prompt = f"Infrastructure Objective:\n{objective}\n\nGenerate the complete architectural blueprint and file-by-file specification."
        
        response = await client.aio.models.generate_content_stream(
            model=self.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=HYBRID_PLANNER_PROMPT,
                temperature=0.2,
            )
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def execute_verification(self) -> str:
        """
        Runs local verification checks (e.g., terraform validate if .tf files exist).
        """
        results = []
        has_tf_files = any(f.endswith(".tf") for _, _, files in os.walk(self.workspace_path) for f in files)
        
        if has_tf_files:
            terraform_bin = shutil.which("terraform") or shutil.which("tofu")
            if terraform_bin:
                results.append(f"🔍 Running Terraform validation using: {terraform_bin}...")
                # 1. terraform init -backend=false
                init_proc = await asyncio.create_subprocess_exec(
                    terraform_bin, f"-chdir={self.workspace_path}", "init", "-backend=false",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await init_proc.communicate()
                if init_proc.returncode != 0:
                    results.append(f"❌ terraform init failed:\n{stderr.decode('utf-8')}")
                else:
                    results.append("✓ terraform init succeeded.")

                # 2. terraform validate
                val_proc = await asyncio.create_subprocess_exec(
                    terraform_bin, f"-chdir={self.workspace_path}", "validate",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await val_proc.communicate()
                val_out = stdout.decode("utf-8") + stderr.decode("utf-8")
                if val_proc.returncode == 0:
                    results.append(f"✅ terraform validate passed!\n{val_out.strip()}")
                else:
                    results.append(f"⚠️ terraform validate issues detected:\n{val_out.strip()}")
            else:
                results.append("⚠️ terraform binary not found in PATH; skipping CLI validation.")
        else:
            results.append("ℹ️ No .tf files detected in workspace for Terraform validation.")

        return "\n".join(results)

    async def execute_swarm(self, objective: str) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Executes the Hybrid Swarm pipeline:
        Stage 1: Cloud Gemini Planner (Streaming)
        Stage 2: Local Gemma 4 Worker (Apple Silicon Metal)
        Stage 3: Automated CLI Verification & Audit
        """
        # Ensure target workspace exists
        os.makedirs(self.workspace_path, exist_ok=True)

        # Stage 1: Cloud Planning
        yield ("PLANNER", f"\n[bold yellow]═══ Stage 1: Cloud Gemini Architect ({self.gemini_model}) ═══[/bold yellow]\n")
        plan_start = time.time()
        plan_tokens = []
        try:
            async for chunk in self.execute_cloud_plan(objective):
                plan_tokens.append(chunk)
                yield ("PLANNER", chunk)
        except Exception as e:
            error_msg = f"\n[bold red][!] Cloud Gemini Planning failed: {str(e)}[/bold red]\n"
            yield ("PLANNER", error_msg)
            return

        plan_duration = time.time() - plan_start
        plan_text = "".join(plan_tokens)
        yield ("PLANNER", f"\n[dim]✓ Cloud Plan generated in {plan_duration:.1f}s[/dim]\n")

        # Stage 2: Local Worker
        yield ("WORKER", f"\n[bold green]═══ Stage 2: Local Gemma 4 Worker (Apple Silicon Metal) ═══[/bold green]\n")
        worker_start = time.time()
        worker_tokens = []
        worker_config = self._create_worker_config()

        async with Agent(worker_config) as worker:
            worker_prompt = (
                f"User Objective:\n{objective}\n\n"
                f"Execution Blueprint from Cloud Architect:\n{plan_text}\n\n"
                f"Target Workspace: {self.workspace_path}\n\n"
                f"Implement this blueprint now using your tools (write_to_file, etc.)."
            )
            resp = await worker.chat(worker_prompt)
            async for token in resp:
                worker_tokens.append(token)
                yield ("WORKER", token)

        worker_duration = time.time() - worker_start
        worker_text = "".join(worker_tokens)
        yield ("WORKER", f"\n[dim]✓ Local Worker completed in {worker_duration:.1f}s[/dim]\n")

        # Stage 3: Automated Verification
        yield ("REVIEWER", f"\n[bold cyan]═══ Stage 3: Local Verification & Quality Audit ═══[/bold cyan]\n")
        verification_output = await self.execute_verification()
        yield ("REVIEWER", f"{verification_output}\n")

        # Session Logging
        if self.session:
            summary = (
                f"### Hybrid Swarm Objective: {objective}\n\n"
                f"**Planner**: Cloud Gemini (`{self.gemini_model}`, {plan_duration:.1f}s)\n"
                f"**Worker**: Local Gemma 4 26B ({worker_duration:.1f}s)\n\n"
                f"#### Architectural Blueprint:\n{plan_text}\n\n"
                f"#### Worker Implementation:\n{worker_text}\n\n"
                f"#### Verification Results:\n```\n{verification_output}\n```\n"
            )
            self.session.append_turn(f"/swarm {objective}", summary)
