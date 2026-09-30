import os
import sys
import argparse
from rich.console import Console
from rich.table import Table

from session_manager import SessionManager

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description="View and manage local agent sessions")
    parser.add_argument("--workspace", "-w", default=os.getcwd(), help="Workspace directory containing sessions")
    parser.add_argument("--delete", "-d", help="Delete session by number (#) or ID")
    parser.add_argument("--transcript", "-t", help="Print transcript for session by number (#) or ID")
    return parser.parse_args()

def show_sessions(workspace: str):
    mgr = SessionManager(workspace)
    sessions = mgr.list_sessions()
    
    if not sessions:
        console.print("[dim yellow]No local sessions found in ./sessions/[/dim yellow]")
        return False

    table = Table(title=f"[bold yellow]Local Gemma Agent Sessions ({mgr.sessions_dir})[/bold yellow]", border_style="yellow")
    table.add_column("#", justify="right", style="bold yellow", width=3)
    table.add_column("Title / First Prompt", style="white", ratio=3)
    table.add_column("Turns", justify="right", style="green", width=6)
    table.add_column("Last Active", style="dim", width=19)
    table.add_column("Session ID", style="dim cyan", width=20)

    for idx, s in enumerate(sessions, 1):
        last_time = s.updated_at[:19].replace("T", " ") if s.updated_at else s.created_at[:19].replace("T", " ")
        short_id = s.session_id[:16] + "…"
        table.add_row(str(idx), s.title, str(s.turn_count), last_time, short_id)

    console.print(table)
    console.print(f"\n[dim]To resume a session:             ./run_tui.sh --resume <#>[/dim]  [dim cyan](e.g. ./run_tui.sh -r 1)[/dim cyan]")
    console.print(f"[dim]To inspect a session transcript: python view_history.py -t <#>[/dim]\n")
    return True

def main():
    args = parse_args()
    mgr = SessionManager(args.workspace)

    if args.delete:
        target = mgr.resolve_session(args.delete)
        if target:
            mgr.delete_session(target.session_id)
            console.print(f"[bold green]✓ Deleted session:[/bold green] {target.title} ({target.session_id})")
        else:
            console.print(f"[bold red][!] Session '{args.delete}' not found.[/bold red]")
        return

    if args.transcript:
        target = mgr.resolve_session(args.transcript)
        if target and target.transcript_file.exists():
            console.print(f"[bold yellow]=== Transcript: {target.title} ({target.session_id}) ===[/bold yellow]\n")
            console.print(target.transcript_file.read_text(encoding="utf-8"))
        else:
            console.print(f"[bold red][!] Transcript not found for session '{args.transcript}'.[/bold red]")
        return

    show_sessions(args.workspace)

if __name__ == "__main__":
    main()
