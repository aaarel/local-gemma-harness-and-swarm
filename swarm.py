import asyncio
import os
import sys
import time
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple

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
            system_instructions=system_instructions,
            save_dir=str(self.session.conversation_dir) if self.session else None,
            app_data_dir=str(self.session.app_data_dir) if self.session else None,
        )

    async def run_stage(self, role_name: str, prompt: str, system_instructions: str, write_allowed: bool = False) -> AsyncGenerator[str, None]:
        config = self._create_role_config(system_instructions, write_allowed=write_allowed)
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                yield token

    async def execute_swarm(self, objective: str) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Executes the 3-stage sequential swarm pipeline:
        Stage 1: Planner
        Stage 2: Worker
        Stage 3: Reviewer
        Yields (stage_name, token) for live streaming.
        """
        # Stage 1: Planning
        yield ("PLANNER", f"\n[bold yellow]═══ Stage 1: Swarm Planner ═══[/bold yellow]\n")
        plan_tokens = []
        plan_config = self._create_role_config(PLANNER_PROMPT, write_allowed=False)
        async with Agent(plan_config) as planner:
            resp = await planner.chat(f"Create an implementation plan for this objective:\n{objective}")
            async for token in resp:
                plan_tokens.append(token)
                yield ("PLANNER", token)
        plan_text = "".join(plan_tokens)

        # Stage 2: Worker Execution
        yield ("WORKER", f"\n\n[bold green]═══ Stage 2: Swarm Worker / Builder ═══[/bold green]\n")
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
        yield ("REVIEWER", f"\n\n[bold cyan]═══ Stage 3: Swarm Reviewer / QA ═══[/bold cyan]\n")
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
            full_swarm_summary = f"### Swarm Objective: {objective}\n\n#### Plan:\n{plan_text}\n\n#### Implementation:\n{worker_text}\n\n#### Review:\n{reviewer_text}"
            self.session.append_turn(f"/swarm {objective}", full_swarm_summary)
