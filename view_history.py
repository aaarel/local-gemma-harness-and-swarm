import os
import glob
import json
import sys
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from session_manager import SessionManager

console = Console()
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")
WORKSPACE = os.path.abspath(os.path.dirname(__file__))

def show_local_sessions():
    mgr = SessionManager(WORKSPACE)
    sessions = mgr.list_sessions()
    
    if not sessions:
        console.print("[dim yellow]No local sessions found in ./sessions/[/dim yellow]")
        return False

    table = Table(title="[bold yellow]Local Gemma 4 Agent Sessions (./sessions/)[/bold yellow]", border_style="yellow")
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
    console.print(f"[dim]To inspect a session transcript: cat sessions/<session_id>/transcript.md[/dim]\n")
    return True

def show_legacy_transcripts():
    transcript_files = glob.glob(f"{BRAIN_DIR}/*/.system_generated/logs/transcript.jsonl")
    if not transcript_files:
        return

    transcript_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    table = Table(title="[bold dim]Legacy SDK Transcripts (~/.gemini/antigravity/brain)[/bold dim]", border_style="dim")
    table.add_column("Time", style="dim", width=19)
    table.add_column("Source", style="cyan", width=10)
    table.add_column("Summary / Prompt", style="white")

    count = 0
    for fpath in transcript_files:
        session_id = fpath.split("/")[-4]
        # Skip current IDE session
        if "6dbbfef0" in session_id or "fb6b7e94" in session_id:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    src = data.get("source", "")
                    content = data.get("content", "")
                    created_at = data.get("created_at", "")[:19].replace("T", " ")

                    if src == "USER_EXPLICIT" and content:
                        clean_prompt = content.replace("<USER_REQUEST>\n", "").replace("\n</USER_REQUEST>", "").strip()
                        if "<ADDITIONAL_METADATA>" in clean_prompt:
                            clean_prompt = clean_prompt.split("<ADDITIONAL_METADATA>")[0].strip()
                        table.add_row(created_at, "[bold cyan]User[/bold cyan]", clean_prompt[:80] + ("..." if len(clean_prompt) > 80 else ""))
                        count += 1
                        if count >= 10:
                            break
        except Exception:
            continue
        if count >= 10:
            break

    if count > 0:
        console.print(table)

def main():
    has_local = show_local_sessions()
    if not has_local or "--all" in sys.argv:
        show_legacy_transcripts()

if __name__ == "__main__":
    main()
