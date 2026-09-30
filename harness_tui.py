import argparse
import asyncio
import os
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path

from google.antigravity import Agent, LiteRTAgentConfig, types
from google.antigravity.hooks import hooks, policy
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from session_manager import SessionManager, Session

MODEL_PATH = os.path.expanduser("~/.litert-lm/models/gemma4-26b/model.litertlm")
WORKSPACE = os.path.abspath(".")
console = Console()

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
        elif stripped.startswith(("- ", "* ")):
            # Bullet points in green
            content = line.lstrip("-* ")
            sys.stdout.write(f"  \033[1;32m•\033[0m \033[32m{content}\033[0m\n")
        else:
            # Standard model text in crisp green
            sys.stdout.write(f"\033[32m{line}\033[0m\n")
        sys.stdout.flush()

# Track tool execution duration
active_tool_start = 0

@hooks.pre_tool_call_decide
async def on_pre_tool(data: types.ToolCall) -> types.HookResult:
    global active_tool_start
    active_tool_start = time.time()
    tool_name = str(data.name).replace("BuiltinTools.", "").lower()

    if "run_command" in tool_name:
        cmd = data.args.get("CommandLine", "")
        console.print(f"\n[bold yellow]⚡ Executing command:[/bold yellow] [dim cyan]{cmd}[/dim cyan]")
    elif "view_file" in tool_name:
        path = data.args.get("AbsolutePath", "")
        console.print(f"\n[bold yellow]⚡ Viewing file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    elif any(w in tool_name for w in ("write_to_file", "create_file")):
        path = data.args.get("TargetFile", "")
        console.print(f"\n[bold yellow]⚡ Creating file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    elif any(e in tool_name for e in ("replace_file_content", "edit_file")):
        path = data.args.get("TargetFile", "")
        console.print(f"\n[bold yellow]⚡ Editing file:[/bold yellow] [dim cyan]{path}[/dim cyan]")
    else:
        console.print(f"\n[bold yellow]⚡ Running tool:[/bold yellow] [dim cyan]{tool_name}[/dim cyan]")

    return types.HookResult(allow=True)

@hooks.post_tool_call
async def on_post_tool(data):
    global active_tool_start
    duration = time.time() - active_tool_start if active_tool_start else 0
    console.print(f"[dim green]✓ Tool completed ({duration:.1f}s)[/dim green]")

def render_sessions_table(sessions: list[Session], current_id: str = ""):
    if not sessions:
        console.print("[dim yellow]No recorded sessions found.[/dim yellow]")
        return

    table = Table(title="[bold yellow]Local Agent Saved Sessions[/bold yellow]", border_style="yellow")
    table.add_column("Session ID", style="cyan", width=22)
    table.add_column("Title", style="white")
    table.add_column("Turns", justify="right", style="green", width=6)
    table.add_column("Last Active", style="dim", width=19)

    for s in sessions:
        marker = " [bold green]◄ Active[/bold green]" if s.session_id == current_id else ""
        last_time = s.updated_at[:19].replace("T", " ") if s.updated_at else s.created_at[:19].replace("T", " ")
        table.add_row(s.session_id, f"{s.title}{marker}", str(s.turn_count), last_time)

    console.print(table)

def render_info_panel(session: Session):
    info_text = (
        f"[bold cyan]Session ID:[/bold cyan] {session.session_id}\n"
        f"[bold cyan]Title:[/bold cyan] {session.title}\n"
        f"[bold cyan]Created At:[/bold cyan] {session.created_at}\n"
        f"[bold cyan]Last Active:[/bold cyan] {session.updated_at}\n"
        f"[bold cyan]Turns Completed:[/bold cyan] {session.turn_count}\n"
        f"[bold cyan]Transcript File:[/bold cyan] {session.transcript_file}\n"
        f"[bold cyan]Trajectory Save Dir:[/bold cyan] {session.conversation_dir}\n"
        f"[bold cyan]Session App Data/Artifacts:[/bold cyan] {session.app_data_dir}"
    )
    console.print(Panel(info_text, title="[bold yellow]Session Information[/bold yellow]", border_style="cyan"))

def parse_args():
    parser = argparse.ArgumentParser(description="Gemma 4 26B Local TUI Harness with Session Management")
    parser.add_argument("--new", "-n", action="store_true", help="Start a new session immediately")
    parser.add_argument("--resume", "-r", nargs="?", const="latest", help="Resume latest or specified session ID")
    parser.add_argument("--list", "-l", action="store_true", help="List all saved sessions and exit")
    parser.add_argument("--title", "-t", type=str, help="Initial title for the session")
    return parser.parse_known_args()[0]

async def select_or_create_session(session_mgr: SessionManager, args: argparse.Namespace) -> Session:
    sessions = session_mgr.list_sessions()

    # 1. Direct CLI flags
    if args.list:
        render_sessions_table(sessions)
        sys.exit(0)

    if args.new:
        session = session_mgr.create_session(title=args.title, model="gemma4-26b")
        console.print(f"[bold green]✓ Created new session:[/bold green] [cyan]{session.title}[/cyan] ({session.session_id})\n")
        return session

    if args.resume:
        if args.resume == "latest":
            latest = session_mgr.get_latest_session()
            if latest:
                console.print(f"[bold green]✓ Resuming latest session:[/bold green] [cyan]{latest.title}[/cyan] ({latest.session_id})\n")
                return latest
            console.print("[dim yellow]No prior session found. Creating a new one.[/dim yellow]")
            return session_mgr.create_session(title=args.title, model="gemma4-26b")
        
        target = session_mgr.get_session(args.resume)
        if target:
            console.print(f"[bold green]✓ Resuming session:[/bold green] [cyan]{target.title}[/cyan] ({target.session_id})\n")
            return target
        console.print(f"[bold red][!] Session '{args.resume}' not found. Starting a new session.[/bold red]")
        return session_mgr.create_session(title=args.title, model="gemma4-26b")

    # 2. Interactive prompt if sessions exist
    if sessions:
        latest = sessions[0]
        console.print(f"[bold cyan]Found recent session:[/bold cyan] \"[white]{latest.title}[/white]\" ([dim]{latest.session_id}[/dim], {latest.turn_count} turns)")
        try:
            choice = input("Press [Enter] to resume, 'n' for new, or 'l' to list all: ").strip().lower()
            if choice == "l":
                render_sessions_table(sessions)
                sub_choice = input("Enter session ID to resume (or [Enter] for new): ").strip()
                if sub_choice:
                    target = session_mgr.get_session(sub_choice)
                    if target:
                        return target
                return session_mgr.create_session(title=args.title, model="gemma4-26b")
            elif choice == "n":
                return session_mgr.create_session(title=args.title, model="gemma4-26b")
            else:
                return latest
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Aborted.[/dim]")
            sys.exit(0)

    # 3. Default: new session
    return session_mgr.create_session(title=args.title, model="gemma4-26b")

async def main():
    args = parse_args()
    session_mgr = SessionManager(WORKSPACE)

    if not os.path.exists(MODEL_PATH):
        console.print(f"[bold red][!] Model not found at: {MODEL_PATH}[/bold red]")
        return

    session = await select_or_create_session(session_mgr, args)

    banner_text = (
        f"[bold cyan]Active Session:[/bold cyan] {session.title} ([dim]{session.session_id}[/dim])\n"
        f"[bold cyan]Turns Completed:[/bold cyan] {session.turn_count}\n"
        f"[bold cyan]Model:[/bold cyan] {MODEL_PATH}\n"
        f"[bold cyan]Engine:[/bold cyan] LiteRT on Apple Silicon Metal GPU ([bold green]100% Offline[/bold green])\n"
        f"[bold cyan]Navigation:[/bold cyan] Arrow keys (←/→ cursor, ↑/↓ history)\n"
        f"[bold cyan]Commands:[/bold cyan] [bold yellow]/sessions[/bold yellow] | [bold yellow]/rename <name>[/bold yellow] | [bold yellow]/info[/bold yellow] | [bold yellow]/history[/bold yellow] | [bold yellow]/exit[/bold yellow]"
    )
    console.print(Panel(banner_text, title="[bold yellow]Gemma 4 26B Local Agent (Antigravity + LiteRT)[/bold yellow]", border_style="yellow"))

    console.print("\n[dim]Loading model weights into unified memory & restoring session state...[/dim]")

    config = LiteRTAgentConfig(
        model_path=MODEL_PATH,
        workspaces=[WORKSPACE],
        policies=[policy.allow_all()],  # Allows autonomous tool execution
        hooks=[on_pre_tool, on_post_tool],  # Real-time tool lifecycle display
        conversation_id=session.session_id,  # Native Antigravity conversation ID
        save_dir=str(session.conversation_dir),  # Persistent trajectory state
        app_data_dir=str(session.app_data_dir),  # Per-session artifacts & scratch files
    )

    prompt_session = PromptSession(
        history=FileHistory(os.path.expanduser("~/.gemma_prompt_history.txt"))
    )
    prompt_style = Style.from_dict({
        "prompt": "ansicyan bold",
        "": "ansicyan",
    })

    try:
        async with Agent(config) as agent:
            console.print("[bold green]✓ Gemma 4 online & ready! Type your prompt below.[/bold green]\n")
            
            while True:
                try:
                    user_prompt = await prompt_session.prompt_async(
                        [("class:prompt", f"You [{session.turn_count + 1}] > ")],
                        style=prompt_style,
                    )
                    user_prompt = user_prompt.strip()

                    if not user_prompt:
                        continue

                    # Slash commands
                    lower_prompt = user_prompt.lower()
                    if lower_prompt in ("/exit", "/quit", "exit", "quit"):
                        console.print("\n[bold yellow]Shutting down local agent. See you next time![/bold yellow]")
                        break

                    if lower_prompt == "/clear":
                        console.print("\n[bold yellow][Conversation reset][/bold yellow]\n")
                        continue

                    if lower_prompt == "/sessions":
                        render_sessions_table(session_mgr.list_sessions(), current_id=session.session_id)
                        console.print()
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
                        render_info_panel(session)
                        console.print()
                        continue

                    if lower_prompt in ("/export", "/transcript"):
                        console.print(f"\n[bold green]Transcript file:[/bold green] [cyan]{session.transcript_file}[/cyan]")
                        if session.transcript_file.exists():
                            size = session.transcript_file.stat().st_size
                            console.print(f"[dim]File size: {size} bytes across {session.turn_count} turns.[/dim]\n")
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
                    response = await agent.chat(user_prompt)
                    
                    # Forward-only streamer guarantees full scrollback and responsive terminal reflow
                    streamer = TerminalMarkdownStreamer()
                    tokens_collected = []
                    async for token in response:
                        tokens_collected.append(token)
                        streamer.feed(token)
                    streamer.flush()

                    elapsed = time.time() - start_time
                    full_response = "".join(tokens_collected)
                    
                    # Persist turn to transcript and update session metadata
                    session.append_turn(user_prompt, full_response, duration_sec=elapsed)

                    console.print(f"\n[dim gray]⏱ Worked for {elapsed:.1f}s | Turn {session.turn_count} saved[/dim gray]\n")

                except (KeyboardInterrupt, EOFError):
                    console.print("\n\n[bold yellow]Session interrupted.[/bold yellow]")
                    break

    finally:
        session.save()
        console.print(Panel(
            f"[bold green]✓ Session successfully preserved:[/bold green] {session.title}\n"
            f"[bold cyan]ID:[/bold cyan] {session.session_id}  |  [bold cyan]Turns:[/bold cyan] {session.turn_count}\n"
            f"[bold cyan]Transcript:[/bold cyan] {session.transcript_file}\n"
            f"[bold yellow]Resume anytime with:[/bold yellow] [white]./run_tui.sh --resume {session.session_id}[/white]",
            title="[bold yellow]Session Saved[/bold yellow]",
            border_style="green"
        ))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
