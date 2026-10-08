import argparse
import asyncio
import os
import re
import sys
import time
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from google.antigravity import Agent, LiteRTAgentConfig, types
from google.antigravity.hooks import hooks, policy
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from session_manager import SessionManager, Session
from swarm import LocalSwarm

DEFAULT_MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")
console = Console()

DEFAULT_SYSTEM_INSTRUCTIONS = """You are Gemma, an expert autonomous software engineer and coding assistant running 100% locally on Apple Silicon via Google AI Edge LiteRT.

CORE OPERATIONAL GUIDELINES:

1. TOOL USAGE & EXECUTION CONSTRAINTS:
   - Only call tools (run_command, view_file, write_to_file, replace_file_content) when explicitly needed to inspect/edit files or run terminal commands.
   - If the user asks a general knowledge or explanation question, answer directly in text without calling tools.
   - If the user explicitly instructs "do not execute", "dry run", or "review only", NEVER invoke execution or modification tools.
   - Before modifying or editing an existing file, always inspect it first using view_file.

2. CODE QUALITY & ACCURACY:
   - Write clean, modular, production-ready code.
   - Do NOT use placeholder comments, omitted blocks, or "// TODO" shortcuts—provide complete, working implementations.
   - Preserve existing project architecture, coding standards, and indentation styles.

3. COMMUNICATION & TERMINAL STREAMING:
   - Keep answers direct, concise, and technically rigorous. Avoid unnecessary conversational filler.
   - Format outputs with clean, standard Markdown (code fences, lists, tables) tailored for terminal readability."""

class TerminalMarkdownStreamer:
    """
    Forward-only streaming markdown formatter.
    Preserves 100% of terminal scrollback, prevents truncation,
    and supports dynamic window reflow without screen redrawing.
    """
    def __init__(self):
        self.in_code = False
        self.buf = ""

    def feed(self, token: str):
        self.buf += token
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._print_line(line)

    def flush(self):
        if self.buf:
            self._print_line(self.buf)
            self.buf = ""
        if self.in_code:
            width = min(60, max(30, shutil.get_terminal_size().columns - 4))
            sys.stdout.write(f"\033[1;36m└{'─' * width}\033[0m\n")
            self.in_code = False
        sys.stdout.flush()

    def _print_line(self, line: str):
        stripped = line.strip()
        width = min(60, max(30, shutil.get_terminal_size().columns - 4))

        if stripped.startswith("```"):
            if not self.in_code:
                self.in_code = True
                lang = stripped[3:].strip() or "code"
                header_border = max(5, width - len(lang) - 6)
                sys.stdout.write(f"\033[1;36m┌── {lang} {'─' * header_border}\033[0m\n")
            else:
                self.in_code = False
                sys.stdout.write(f"\033[1;36m└{'─' * width}\033[0m\n")
            sys.stdout.flush()
            return

        if self.in_code:
            # Code block lines styled in distinct yellow with vertical border
            sys.stdout.write(f"\033[36m│\033[0m \033[33m{line}\033[0m\n")
        elif stripped.startswith(("# ", "## ", "### ", "#### ")):
            # Markdown headers in bold yellow
            sys.stdout.write(f"\033[1;33m{line}\033[0m\n")
        else:
            # Regex match for bullets to preserve indentation & avoid stripping bold (**Bold**) markers
            bullet_match = re.match(r"^(\s*)[-*]\s+(.*)$", line)
            if bullet_match:
                indent, content = bullet_match.group(1), bullet_match.group(2)
                sys.stdout.write(f"{indent}\033[1;32m•\033[0m \033[32m{content}\033[0m\n")
            else:
                # Standard model text in crisp green
                sys.stdout.write(f"\033[32m{line}\033[0m\n")
        sys.stdout.flush()

# Tool runtime tracking (keyed by tool call ID for concurrency safety)
active_tools: Dict[str, Tuple[float, str, Dict[str, Any]]] = {}
current_streamer: Optional[TerminalMarkdownStreamer] = None
current_session: Optional[Session] = None
yolo_mode: bool = False
prompt_session: Optional[PromptSession] = None
prompt_style = Style.from_dict({
    "prompt": "ansicyan bold",
    "": "ansicyan",
})

@hooks.pre_tool_call_decide
async def on_pre_tool(data: types.ToolCall) -> types.HookResult:
    global active_tools, current_streamer, yolo_mode, current_session, prompt_session
    
    # Flush pending tokens before printing tool notice
    if current_streamer:
        current_streamer.flush()

    call_id = getattr(data, "id", None) or f"{data.name}_{time.time()}"
    tool_name = str(data.name).replace("BuiltinTools.", "").lower()
    tool_args = getattr(data, "args", {}) or {}
    active_tools[call_id] = (time.time(), tool_name, tool_args)

    # Format human-readable preview
    if "run_command" in tool_name:
        cmd = tool_args.get("CommandLine", "") or json.dumps(tool_args)
        console.print(f"\n[bold yellow]⚡ Executing command:[/bold yellow] [dim cyan]{cmd}[/dim cyan]")
    elif "view_file" in tool_name:
        path = tool_args.get("AbsolutePath", "") or json.dumps(tool_args)
        console.print(f"\n[bold yellow]⚡ Viewing file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    elif any(w in tool_name for w in ("write_to_file", "create_file")):
        path = tool_args.get("TargetFile", "") or json.dumps(tool_args)
        console.print(f"\n[bold yellow]⚡ Creating file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    elif any(e in tool_name for e in ("replace_file_content", "edit_file")):
        path = tool_args.get("TargetFile", "") or json.dumps(tool_args)
        console.print(f"\n[bold yellow]⚡ Editing file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    else:
        summary = json.dumps(tool_args, ensure_ascii=False)[:80]
        console.print(f"\n[bold yellow]⚡ Running tool:[/bold yellow] [dim cyan]{tool_name}({summary})[/dim cyan]")

    # Safety Policy: Write and execution tools require confirmation unless in YOLO mode
    is_write_or_exec = any(k in tool_name for k in ("run_command", "write_to_file", "replace_file_content", "create_file", "edit_file", "delete_file"))
    if is_write_or_exec and not yolo_mode and prompt_session:
        console.print(f"[bold red]⚠️  Safety Confirmation Required for:[/bold red] [white]{tool_name}[/white]")
        ans = await prompt_session.prompt_async(
            [("class:prompt", "Allow execution? [y/N/a(lways)]: ")],
            style=prompt_style,
        )
        ans = ans.strip().lower()
        if ans == "a":
            yolo_mode = True
            console.print("[dim green]✓ Autonomous (YOLO) mode enabled for remainder of session.[/dim green]\n")
            return types.HookResult(allow=True)
        elif ans in ("y", "yes"):
            return types.HookResult(allow=True)
        else:
            console.print("[dim red]✗ Execution denied by user.[/dim red]\n")
            if current_session:
                current_session.log_tool_call(tool_name, tool_args, 0.0, allowed=False, error="Denied by user")
            return types.HookResult(allow=False, reason="Tool execution denied by user.")

    return types.HookResult(allow=True)

@hooks.post_tool_call
async def on_post_tool(data):
    global active_tools, current_session
    call_id = getattr(data, "id", None) or str(getattr(data, "name", ""))
    start_info = active_tools.pop(call_id, None)
    duration = time.time() - start_info[0] if start_info else 0.0
    tool_name = start_info[1] if start_info else str(getattr(data, "name", "tool"))
    tool_args = start_info[2] if start_info else {}
    err = getattr(data, "error", None)

    if err:
        console.print(f"[bold red]✗ Tool failed ({duration:.1f}s): {err}[/bold red]")
    else:
        console.print(f"[dim green]✓ Tool completed ({duration:.1f}s)[/dim green]")

    if current_session:
        current_session.log_tool_call(tool_name, tool_args, duration, allowed=True, error=str(err) if err else None)

def render_sessions_table(sessions: list[Session], current_id: str = ""):
    if not sessions:
        console.print("[dim yellow]No recorded sessions found.[/dim yellow]")
        return

    table = Table(title="[bold yellow]Local Agent Saved Sessions[/bold yellow]", border_style="yellow")
    table.add_column("#", justify="right", style="bold yellow", width=3)
    table.add_column("Title", style="white", ratio=3)
    table.add_column("Turns", justify="right", style="green", width=6)
    table.add_column("Last Active", style="dim", width=19)
    table.add_column("Session ID", style="dim cyan", width=20)

    for idx, s in enumerate(sessions, 1):
        marker = " [bold green]◄ Active[/bold green]" if s.session_id == current_id else ""
        last_time = s.updated_at[:19].replace("T", " ") if s.updated_at else s.created_at[:19].replace("T", " ")
        short_id = s.session_id[:16] + "…"
        table.add_row(str(idx), f"{s.title}{marker}", str(s.turn_count), last_time, short_id)

    console.print(table)

def render_info_panel(session: Session, workspace: str, model_path: str):
    info_text = (
        f"[bold cyan]Session ID:[/bold cyan] {session.session_id}\n"
        f"[bold cyan]Title:[/bold cyan] {session.title}\n"
        f"[bold cyan]Model:[/bold cyan] {model_path}\n"
        f"[bold cyan]Workspace:[/bold cyan] {workspace}\n"
        f"[bold cyan]Mode:[/bold cyan] {'[red]YOLO (Autonomous)[/red]' if yolo_mode else '[green]Protected (Confirm Writes)[/green]'}\n"
        f"[bold cyan]Turns Completed:[/bold cyan] {session.turn_count}\n"
        f"[bold cyan]Created At:[/bold cyan] {session.created_at}\n"
        f"[bold cyan]Last Active:[/bold cyan] {session.updated_at}\n"
        f"[bold cyan]Transcript:[/bold cyan] {session.transcript_file}\n"
        f"[bold cyan]Events Log:[/bold cyan] {session.events_file}\n"
        f"[bold cyan]Trajectory Save Dir:[/bold cyan] {session.conversation_dir}"
    )
    console.print(Panel(info_text, title="[bold yellow]Session Information[/bold yellow]", border_style="cyan"))

def parse_args():
    parser = argparse.ArgumentParser(description="Gemma 4 26B Local TUI Harness with Session Management & Safety Controls")
    parser.add_argument("--new", "-n", action="store_true", help="Start a new session immediately")
    parser.add_argument("--resume", "-r", nargs="?", const="latest", help="Resume latest or specified session by number (#) or ID")
    parser.add_argument("--list", "-l", action="store_true", help="List all saved sessions and exit")
    parser.add_argument("--delete", "-d", type=str, help="Delete a session by number (#) or ID and exit")
    parser.add_argument("--yolo", action="store_true", help="Autonomous mode: auto-approve write tools without confirmation")
    parser.add_argument("--workspace", "-w", type=str, default=os.getcwd(), help="Target workspace path (defaults to current directory)")
    parser.add_argument("--model", "-m", type=str, default=DEFAULT_MODEL_PATH, help="Path to .litertlm model file")
    parser.add_argument("--title", "-t", type=str, help="Initial title for the session")
    parser.add_argument("--system-prompt", "-s", type=str, default=None, help="Custom system instructions override")
    return parser.parse_known_args()[0]

async def select_or_create_session(session_mgr: SessionManager, args: argparse.Namespace, p_session: PromptSession) -> Session:
    sessions = session_mgr.list_sessions()

    # 1. Direct CLI flags
    if args.list:
        render_sessions_table(sessions)
        sys.exit(0)

    if args.delete:
        target = session_mgr.resolve_session(args.delete)
        if target:
            session_mgr.delete_session(target.session_id)
            console.print(f"[bold green]✓ Deleted session:[/bold green] {target.title} ({target.session_id})")
        else:
            console.print(f"[bold red][!] Session '{args.delete}' not found.[/bold red]")
        sys.exit(0)

    if args.new:
        session = session_mgr.create_session(title=args.title, model="gemma4-26b")
        console.print(f"[bold green]✓ Created new session:[/bold green] [cyan]{session.title}[/cyan] ({session.session_id})\n")
        return session

    if args.resume:
        target = session_mgr.resolve_session(args.resume)
        if target:
            console.print(f"[bold green]✓ Resuming session:[/bold green] [cyan]{target.title}[/cyan] ({target.session_id})\n")
            return target
        console.print(f"[bold red][!] Session '{args.resume}' not found. Starting a new session.[/bold red]")
        return session_mgr.create_session(title=args.title, model="gemma4-26b")

    # 2. Interactive selection using PromptSession (obeying rule: never use plain input())
    if sessions:
        latest = sessions[0]
        console.print(f"[bold cyan]Found recent session:[/bold cyan] \"[white]{latest.title}[/white]\" (Turns: {latest.turn_count})")
        try:
            prompt_hint = f"Press [Enter] to resume #1, number (1-{len(sessions)}), 'l' to list, 'n' for new: "
            choice = await p_session.prompt_async([("class:prompt", prompt_hint)], style=prompt_style)
            choice = choice.strip()
            if not choice:
                return latest
            if choice.lower() == "n":
                return session_mgr.create_session(title=args.title, model="gemma4-26b")
            if choice.lower() == "l":
                render_sessions_table(sessions)
                sub_choice = await p_session.prompt_async(
                    [("class:prompt", f"Enter session # (1-{len(sessions)}) or ID to resume (or [Enter] for new): ")],
                    style=prompt_style
                )
                sub_choice = sub_choice.strip()
                if sub_choice:
                    target = session_mgr.resolve_session(sub_choice)
                    if target:
                        return target
                return session_mgr.create_session(title=args.title, model="gemma4-26b")
            
            # Direct numeric (#) or ID resolution
            target = session_mgr.resolve_session(choice)
            if target:
                return target
            return session_mgr.create_session(title=args.title, model="gemma4-26b")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Aborted.[/dim]")
            sys.exit(0)

    # 3. Default: new session
    return session_mgr.create_session(title=args.title, model="gemma4-26b")

async def main():
    global current_session, current_streamer, yolo_mode, prompt_session
    args = parse_args()
    yolo_mode = args.yolo
    workspace_path = os.path.abspath(args.workspace)
    model_path = os.path.abspath(os.path.expanduser(args.model))

    session_mgr = SessionManager(workspace_path)

    if not os.path.exists(model_path):
        console.print(f"[bold red][!] Model not found at: {model_path}[/bold red]")
        return

    prompt_session = PromptSession(
        history=FileHistory(os.path.expanduser("~/.gemma_prompt_history.txt"))
    )

    session = await select_or_create_session(session_mgr, args, prompt_session)
    current_session = session

    mode_badge = "[bold red]YOLO (Autonomous)[/bold red]" if yolo_mode else "[bold green]Protected (Confirm Writes)[/bold green]"
    banner_text = (
        f"[bold cyan]Active Session:[/bold cyan] {session.title} ([dim]{session.session_id}[/dim])\n"
        f"[bold cyan]Safety Mode:[/bold cyan] {mode_badge}\n"
        f"[bold cyan]Workspace:[/bold cyan] {workspace_path}\n"
        f"[bold cyan]Model:[/bold cyan] {model_path}\n"
        f"[bold cyan]Engine:[/bold cyan] LiteRT on Apple Silicon Metal GPU ([bold green]100% Offline[/bold green])\n"
        f"[bold cyan]Commands:[/bold cyan] [bold yellow]/sessions[/bold yellow] | [bold yellow]/swarm <task>[/bold yellow] | [bold yellow]/delete <#>[/bold yellow] | [bold yellow]/rename <name>[/bold yellow] | [bold yellow]/info[/bold yellow] | [bold yellow]/clear[/bold yellow] | [bold yellow]/exit[/bold yellow]"
    )
    console.print(Panel(banner_text, title="[bold yellow]Gemma 4 Local Agent (Antigravity + LiteRT)[/bold yellow]", border_style="yellow"))

    console.print("\n[dim]Loading model weights into unified memory & restoring session state...[/dim]")

    system_instructions = DEFAULT_SYSTEM_INSTRUCTIONS
    if args.system_prompt:
        if os.path.isfile(args.system_prompt):
            with open(args.system_prompt, "r", encoding="utf-8") as f:
                system_instructions = f.read()
        else:
            system_instructions = args.system_prompt

    config = LiteRTAgentConfig(
        model_path=model_path,
        workspaces=[workspace_path],
        policies=[policy.allow_all()],  # SDK policies allow hook to manage confirmations
        hooks=[on_pre_tool, on_post_tool],  # Hook enforces safety confirmations
        system_instructions=system_instructions,
        conversation_id=session.session_id,  # Native Antigravity conversation ID
        session_continuation_mode=types.SessionContinuationMode.CREATE_OR_RESUME,
        save_dir=str(session.conversation_dir),  # Persistent trajectory state
        app_data_dir=str(session.app_data_dir),  # Per-session artifacts & scratch files
    )

    try:
        async with Agent(config) as agent:
            console.print("[bold green]✓ Gemma 4 online & ready! Type your prompt below.[/bold green]\n")
            
            while True:
                try:
                    user_prompt = await prompt_session.prompt_async(
                        [("class:prompt", f"You [{session.turn_count + 1}] > ")],
                        style=prompt_style,
                    )
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[bold yellow]Shutting down local agent. See you next time![/bold yellow]")
                    break

                user_prompt = user_prompt.strip()
                if not user_prompt:
                    continue

                # Slash commands
                lower_prompt = user_prompt.lower()
                if lower_prompt in ("/exit", "/quit", "exit", "quit"):
                    console.print("\n[bold yellow]Shutting down local agent. See you next time![/bold yellow]")
                    break

                if lower_prompt == "/clear":
                    # Working /clear: resets terminal visual buffer and starts new turn sequence
                    console.clear()
                    console.print(f"[bold yellow][Conversation view cleared — Session #{session.session_id} active][/bold yellow]\n")
                    session.log_event("context_cleared", {"turn": session.turn_count})
                    continue

                if lower_prompt == "/sessions":
                    render_sessions_table(session_mgr.list_sessions(), current_id=session.session_id)
                    console.print()
                    continue

                if lower_prompt.startswith("/delete"):
                    parts = user_prompt.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        target_id = parts[1].strip()
                        target = session_mgr.resolve_session(target_id)
                        if target:
                            if target.session_id == session.session_id:
                                console.print("[yellow]Cannot delete active session while in use.[/yellow]\n")
                            else:
                                session_mgr.delete_session(target.session_id)
                                console.print(f"[bold green]✓ Deleted session:[/bold green] {target.title} ({target.session_id})\n")
                        else:
                            console.print(f"[red]Session '{target_id}' not found.[/red]\n")
                    else:
                        console.print("[yellow]Usage: /delete <# or session ID>[/yellow]\n")
                    continue

                if lower_prompt.startswith("/swarm"):
                    parts = user_prompt.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        objective = parts[1].strip()
                        console.print(f"\n[bold yellow]🐝 Launching Swarm (Planner → Worker → Reviewer)...[/bold yellow]")
                        swarm = LocalSwarm(model_path, workspace_path, session=session)
                        streamer = TerminalMarkdownStreamer()
                        try:
                            async for stage, token in swarm.execute_swarm(objective):
                                streamer.feed(token)
                            streamer.flush()
                            console.print(f"\n[bold green]✓ Swarm pipeline completed! Turn {session.turn_count} saved.[/bold green]\n")
                        except (KeyboardInterrupt, asyncio.CancelledError):
                            streamer.flush()
                            console.print("\n[bold yellow]⚡ Swarm execution aborted by user.[/bold yellow]\n")
                    else:
                        console.print("[yellow]Usage: /swarm <task description or objective>[/yellow]\n")
                    continue

                if lower_prompt.startswith("/rename"):
                    parts = user_prompt.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        new_name = parts[1].strip()
                        session.update_title(new_name)
                        console.print(f"[bold green]✓ Session renamed to:[/bold green] [white]{new_name}[/white]\n")
                    else:
                        console.print("[yellow]Usage: /rename <new session title>[/yellow]\n")
                    continue

                if lower_prompt == "/info":
                    render_info_panel(session, workspace_path, model_path)
                    console.print()
                    continue

                if lower_prompt in ("/export", "/transcript"):
                    console.print(f"\n[bold green]Transcript file:[/bold green] [cyan]{session.transcript_file}[/cyan]")
                    console.print(f"[bold green]Structured events:[/bold green] [cyan]{session.events_file}[/cyan]")
                    if session.transcript_file.exists():
                        size = session.transcript_file.stat().st_size
                        console.print(f"[dim]Transcript size: {size} bytes across {session.turn_count} turns.[/dim]\n")
                    continue

                if lower_prompt == "/history":
                    hist_path = os.path.expanduser("~/.gemma_prompt_history.txt")
                    if os.path.exists(hist_path):
                        with open(hist_path, "r", encoding="utf-8") as hf:
                            lines = [l.lstrip("+").strip() for l in hf if l.strip() and not l.startswith("#")]
                        console.print("\n[bold yellow]── Recent Prompts History ──[/bold yellow]")
                        for idx, p in enumerate(lines[-15:], 1):
                            console.print(f"  [dim cyan]{idx:2d}.[/dim cyan] [white]{p}[/white]")
                        console.print(f"[dim]History file: {hist_path}[/dim]\n")
                    else:
                        console.print("\n[dim]No prompt history recorded yet.[/dim]\n")
                    continue

                console.print("\n[bold green]Gemma 4 >[/bold green]")
                start_time = time.time()
                streamer = TerminalMarkdownStreamer()
                current_streamer = streamer
                tokens_collected = []

                # Turn-level interrupt handling: Ctrl+C mid-answer saves partial output and keeps session alive!
                try:
                    response = await agent.chat(user_prompt)
                    async for token in response:
                        tokens_collected.append(token)
                        streamer.feed(token)
                    streamer.flush()
                    elapsed = time.time() - start_time
                    full_response = "".join(tokens_collected)
                    session.append_turn(user_prompt, full_response, duration_sec=elapsed)
                    console.print(f"\n[dim gray]⏱ Worked for {elapsed:.1f}s | Turn {session.turn_count} saved[/dim gray]\n")
                except (KeyboardInterrupt, asyncio.CancelledError):
                    streamer.flush()
                    elapsed = time.time() - start_time
                    partial_response = "".join(tokens_collected)
                    session.append_interrupted_turn(user_prompt, partial_response, duration_sec=elapsed)
                    console.print(f"\n[bold yellow]⚡ Turn interrupted by user (Ctrl+C). Partial response preserved in session.[/bold yellow]\n")
                    continue
                finally:
                    current_streamer = None

    finally:
        session.save()
        console.print(Panel(
            f"[bold green]✓ Session successfully preserved:[/bold green] {session.title}\n"
            f"[bold cyan]ID:[/bold cyan] {session.session_id}  |  [bold cyan]Turns:[/bold cyan] {session.turn_count}\n"
            f"[bold cyan]Transcript:[/bold cyan] {session.transcript_file}\n"
            f"[bold cyan]Events Log:[/bold cyan] {session.events_file}\n"
            f"[bold yellow]Resume anytime with:[/bold yellow] [white]./run_tui.sh --resume {session.session_id}[/white]",
            title="[bold yellow]Session Saved[/bold yellow]",
            border_style="green"
        ))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
