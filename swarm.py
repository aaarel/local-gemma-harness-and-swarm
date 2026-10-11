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

# =====================================================================
# Local Swarm Prompts
# =====================================================================

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

# =====================================================================
# Cloud Fabric FAST / Hybrid Architecture Prompts
# =====================================================================

HYBRID_PLANNER_PROMPT = """You are a GOOGLE CLOUD PROFESSIONAL SERVICES (PSO) LEAD ARCHITECT specializing in Cloud Foundation Fabric FAST.
Your partner is an on-device AI coding agent (Gemma 4 running locally on Apple Silicon Metal) equipped with file authoring and shell tools.

Your task is to analyze the user's infrastructure objective and emit a structured, production-grade Execution Blueprint for an off-the-shelf Google Cloud Foundation Fabric FAST landing zone for a small customer.

Strict guidelines for your plan:
1. FABRIC FAST STAGE ARCHITECTURE:
   - 0-bootstrap: Automation project, Terraform state GCS bucket, CI/CD SAs, billing alerts, org log sink.
   - 1-resman: Resource hierarchy (Platform and Workloads folders), CIS GCP Org Policies, group IAM bindings.
   - 2-networking: Single Shared VPC with prod and dev subnets in the primary region, Cloud NAT, Private Google Access, firewall rules.
   - 3-project-factory: Workload tenant project attached as a service project to the Shared VPC with Workload Identity.
2. FILE-BY-FILE SPECIFICATION:
   Detail every single file to create across the 4 stages (main.tf, variables.tf, outputs.tf, terraform.tfvars.example) and the operational RUNBOOK.md.
3. OPERATIONAL RUNBOOK (RUNBOOK.md):
   Specify the exact structure of the runbook: Prerequisites, Day-0 local bootstrap execution, state migration to GCS, sequential stage execution order, and Day-2 operations.
4. CIS GCP BENCHMARK GUARDRAILS:
   Enforce CIS GCP v3.0 Level 1 controls (no default VPC, no external SA keys, uniform bucket access, private Google access).

Be precise, structured, and authoritative. Do not ask questions; emit the complete execution blueprint."""

HYBRID_WORKER_PROMPT = """You are the ON-DEVICE IMPLEMENTATION WORKER in a hybrid AI software engineering swarm.
You run 100% locally on Apple Silicon Metal with full access to Antigravity tools (write_to_file, replace_file_content, run_command, view_file).

Your task:
1. Review the Execution Blueprint provided by the Cloud Architect (Gemini).
2. Execute the plan by creating all required stage files in the target workspace using `write_to_file`.
3. Scaffold the complete Cloud Foundation Fabric FAST stages (0-bootstrap, 1-resman, 2-networking, 3-project-factory) with complete, syntactically valid Terraform code and sample .tfvars.
4. Author a comprehensive, production-ready `RUNBOOK.md` with complete operational instructions for the cloud engineer.
5. Execute verification commands using `run_command` (e.g. `terraform validate`).
6. Report a clean summary of files created and verification outcomes."""

SECURITY_AUDITOR_PROMPT = """You are the INDEPENDENT CLOUD SECURITY AUDITOR & CIS BENCHMARK REVIEWER.
You are running in a fresh, isolated evaluation session. Your job is to critically review the Terraform infrastructure files and RUNBOOK.md in the target workspace.

Evaluate against CIS Google Cloud Platform Foundation Benchmark v3.0 (Level 1) & Cloud Foundation Fabric standards:
1. Stage 00 (0-bootstrap): GCS state bucket uniform bucket-level access, versioning, audit log sink.
2. Stage 01 (1-resman): Essential Org Policies (compute.skipDefaultNetworkCreation, iam.disableServiceAccountKeyCreation, storage.uniformBucketLevelAccess), group IAM.
3. Stage 02 (2-networking): Single Shared VPC, private Google access on subnets, Cloud NAT for egress (no public IPs on VMs), secure firewall rules.
4. Stage 03 (3-project-factory): Workload Identity, least-privilege service account bindings.
5. RUNBOOK.md: Complete step-by-step clarity, prerequisite roles, execution order.

Output an Audit Report formatted as:
### 🛡️ Security & Compliance Audit Report
- Status: [PASS] or [REVISION NEEDED]
- Critical / High Findings (if any with exact remediation diffs):
- Medium / Low Recommendations:
- Final Verification Verdict:"""


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
    Stage 1: Cloud Gemini (Architect / Planner) via Antigravity CLI (agy) or google-genai SDK.
    Stage 2: Local Gemma 4 26B (Worker / Coder) via LiteRT on Apple Silicon Metal.
    Stage 3: Local Gemma 4 26B (Security & Compliance Auditor in isolated context).
    Stage 4: Automated Iteration / Remediation (if fixes are requested).
    Stage 5: Automated CLI Verification (terraform validate).
    """
    def __init__(
        self,
        model_path: str,
        workspace_path: str,
        cloud_backend: str = "agy",
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        session: Optional[Session] = None,
    ):
        self.model_path = model_path
        self.workspace_path = workspace_path
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.session = session

        # Automatically select agy CLI backend if available and no API key explicitly provided
        if cloud_backend == "agy" or (not self.gemini_api_key and shutil.which("agy")):
            self.cloud_backend = "agy"
        else:
            self.cloud_backend = "genai"

    def _create_worker_config(self) -> LiteRTAgentConfig:
        return LiteRTAgentConfig(
            model_path=self.model_path,
            workspaces=[self.workspace_path],
            policies=[policy.allow_all()],
            system_instructions=types.CustomSystemInstructions(text=HYBRID_WORKER_PROMPT),
            save_dir=str(self.session.conversation_dir) if self.session else None,
            app_data_dir=str(self.session.app_data_dir) if self.session else None,
        )

    def _create_reviewer_config(self) -> LiteRTAgentConfig:
        return LiteRTAgentConfig(
            model_path=self.model_path,
            workspaces=[self.workspace_path],
            policies=[policy.allow(types.BuiltinTools.VIEW_FILE)],
            system_instructions=types.CustomSystemInstructions(text=SECURITY_AUDITOR_PROMPT),
            conversation_id=f"{self.session.session_id}_sec" if self.session else None,
            save_dir=str(self.session.conversation_dir) if self.session else None,
            app_data_dir=str(self.session.app_data_dir) if self.session else None,
        )

    async def _execute_cloud_plan_via_agy(self, objective: str) -> AsyncGenerator[str, None]:
        """
        Streams architectural plan using the local Antigravity CLI (agy) without requiring an API key.
        """
        agy_bin = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
        if not os.path.exists(agy_bin):
            raise FileNotFoundError(f"Antigravity CLI (agy) not found at: {agy_bin}")

        prompt = f"{HYBRID_PLANNER_PROMPT}\n\nObjective:\n{objective}"
        proc = await asyncio.create_subprocess_exec(
            agy_bin, "--print", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8")

        await proc.wait()
        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise RuntimeError(f"agy CLI failed with code {proc.returncode}: {stderr.decode('utf-8')}")

    async def _execute_cloud_plan_via_genai(self, objective: str) -> AsyncGenerator[str, None]:
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

    async def execute_cloud_plan(self, objective: str) -> AsyncGenerator[str, None]:
        """
        Dispatches cloud planning to either Antigravity CLI (agy) or direct google-genai SDK.
        """
        if self.cloud_backend == "agy":
            async for chunk in self._execute_cloud_plan_via_agy(objective):
                yield chunk
        else:
            async for chunk in self._execute_cloud_plan_via_genai(objective):
                yield chunk

    async def execute_verification(self) -> str:
        """
        Runs local verification checks (e.g., terraform validate if .tf files exist across stages).
        """
        results = []
        terraform_bin = shutil.which("terraform") or shutil.which("tofu")
        
        if not terraform_bin:
            return "⚠️ terraform binary not found in PATH; skipping CLI validation."

        stage_dirs = []
        for root, dirs, files in os.walk(self.workspace_path):
            if any(f.endswith(".tf") for f in files):
                stage_dirs.append(root)

        if not stage_dirs:
            return "ℹ️ No .tf files detected in workspace for Terraform validation."

        results.append(f"🔍 Running Terraform validation using: {terraform_bin}...")
        for stage_dir in sorted(stage_dirs):
            rel_dir = os.path.relpath(stage_dir, self.workspace_path)
            # 1. init
            init_proc = await asyncio.create_subprocess_exec(
                terraform_bin, f"-chdir={stage_dir}", "init", "-backend=false",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await init_proc.communicate()

            # 2. validate
            val_proc = await asyncio.create_subprocess_exec(
                terraform_bin, f"-chdir={stage_dir}", "validate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await val_proc.communicate()
            val_out = stdout.decode("utf-8") + stderr.decode("utf-8")
            if val_proc.returncode == 0:
                results.append(f"  ✓ [{rel_dir}] validate passed!")
            else:
                results.append(f"  ⚠️ [{rel_dir}] issues:\n{val_out.strip()}")

        return "\n".join(results)

    async def execute_swarm(self, objective: str) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Executes the Hybrid Swarm pipeline with Security Audit and Remediation:
        Stage 1: Cloud Gemini Architect via agy CLI / genai
        Stage 2: Local Gemma 4 Worker on Metal
        Stage 3: Local Gemma 4 Security Auditor (Isolated context)
        Stage 4: Fix Iteration Loop (if needed)
        Stage 5: Automated CLI Verification
        """
        os.makedirs(self.workspace_path, exist_ok=True)

        # -------------------------------------------------------------
        # Stage 1: Cloud Gemini Planning
        # -------------------------------------------------------------
        backend_label = "Antigravity CLI (agy)" if self.cloud_backend == "agy" else f"Google GenAI ({self.gemini_model})"
        yield ("PLANNER", f"\n[bold yellow]═══ Stage 1: Cloud Gemini Architect [{backend_label}] ═══[/bold yellow]\n")
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

        # -------------------------------------------------------------
        # Stage 2: Local Gemma Worker (Implementation)
        # -------------------------------------------------------------
        yield ("WORKER", f"\n[bold green]═══ Stage 2: Local Gemma 4 Worker (Apple Silicon Metal) ═══[/bold green]\n")
        worker_start = time.time()
        worker_tokens = []
        worker_config = self._create_worker_config()

        async with Agent(worker_config) as worker:
            worker_prompt = (
                f"User Objective:\n{objective}\n\n"
                f"Execution Blueprint from Cloud Architect:\n{plan_text}\n\n"
                f"Target Workspace: {self.workspace_path}\n\n"
                f"Scaffold the complete Cloud Foundation Fabric FAST landing zone and write RUNBOOK.md now."
            )
            resp = await worker.chat(worker_prompt)
            async for token in resp:
                worker_tokens.append(token)
                yield ("WORKER", token)

        worker_duration = time.time() - worker_start
        worker_text = "".join(worker_tokens)
        yield ("WORKER", f"\n[dim]✓ Local Worker completed in {worker_duration:.1f}s[/dim]\n")

        # -------------------------------------------------------------
        # Stage 3: Independent Security Audit (Isolated Context)
        # -------------------------------------------------------------
        yield ("REVIEWER", f"\n[bold cyan]═══ Stage 3: Security & Compliance Audit (Fresh Context) ═══[/bold cyan]\n")
        sec_start = time.time()
        sec_tokens = []
        reviewer_config = self._create_reviewer_config()

        async with Agent(reviewer_config) as auditor:
            audit_prompt = (
                f"Inspect all files in workspace {self.workspace_path}.\n"
                f"Review the generated Cloud Foundation Fabric FAST stages and RUNBOOK.md against CIS GCP Benchmark v3.0 Level 1.\n"
                "Deliver your security audit report with [PASS] or [REVISION NEEDED]."
            )
            resp = await auditor.chat(audit_prompt)
            async for token in resp:
                sec_tokens.append(token)
                yield ("REVIEWER", token)

        sec_duration = time.time() - sec_start
        audit_text = "".join(sec_tokens)
        yield ("REVIEWER", f"\n[dim]✓ Security Audit completed in {sec_duration:.1f}s[/dim]\n")

        # -------------------------------------------------------------
        # Stage 4: Remediation Pass (If Reviewer requested fixes)
        # -------------------------------------------------------------
        if "REVISION NEEDED" in audit_text.upper():
            yield ("WORKER", f"\n[bold yellow]═══ Stage 4: Applying Security Reviewer Fixes ═══[/bold yellow]\n")
            fix_tokens = []
            async with Agent(self._create_worker_config()) as fixer:
                fix_prompt = (
                    f"The Security Auditor reported these findings:\n{audit_text}\n\n"
                    f"Target Workspace: {self.workspace_path}\n\n"
                    "Please inspect the files and apply the necessary fixes using replace_file_content or write_to_file."
                )
                resp = await fixer.chat(fix_prompt)
                async for token in resp:
                    fix_tokens.append(token)
                    yield ("WORKER", token)
            yield ("WORKER", f"\n[dim]✓ Security fixes applied[/dim]\n")

        # -------------------------------------------------------------
        # Stage 5: Automated CLI Verification
        # -------------------------------------------------------------
        yield ("REVIEWER", f"\n[bold cyan]═══ Stage 5: Automated CLI Verification (terraform validate) ═══[/bold cyan]\n")
        verification_output = await self.execute_verification()
        yield ("REVIEWER", f"{verification_output}\n")

        # Session Logging
        if self.session:
            summary = (
                f"### Fabric FAST Swarm Objective: {objective}\n\n"
                f"**Planner**: Cloud Gemini ({backend_label}, {plan_duration:.1f}s)\n"
                f"**Worker**: Local Gemma 4 26B ({worker_duration:.1f}s)\n"
                f"**Security Auditor**: Local Gemma 4 26B ({sec_duration:.1f}s)\n\n"
                f"#### Architectural Blueprint:\n{plan_text}\n\n"
                f"#### Implementation & Runbook:\n{worker_text}\n\n"
                f"#### Security Audit Verdict:\n{audit_text}\n\n"
                f"#### Verification Results:\n```\n{verification_output}\n```\n"
            )
            self.session.append_turn(f"/fast {objective}", summary)
