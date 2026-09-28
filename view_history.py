import os
import glob
import json
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")

def main():
    transcript_files = glob.glob(f"{BRAIN_DIR}/*/.system_generated/logs/transcript.jsonl")
    if not transcript_files:
        console.print("[yellow]No session logs found.[/yellow]")
        return

    # Sort transcripts by modification time (most recent first)
    transcript_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    table = Table(title="[bold yellow]Recent Local Agent Sessions & Prompts[/bold yellow]", border_style="yellow")
    table.add_column("Time", style="dim", width=19)
    table.add_column("Source", style="cyan", width=10)
    table.add_column("Summary / Prompt", style="white")

    for fpath in transcript_files:
        session_id = fpath.split("/")[-4]
        # Skip the active Antigravity IDE Gemini conversation
        if session_id == "6dbbfef0-18b1-4ed6-a7e7-08b7c6e70b7a":
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    data = json.loads(line)
                    src = data.get("source", "")
                    content = data.get("content", "")
                    created_at = data.get("created_at", "")[:19].replace("T", " ")

                    if src == "USER_EXPLICIT" and content:
                        clean_prompt = content.replace("<USER_REQUEST>\n", "").replace("\n</USER_REQUEST>", "").strip()
                        # Clean extra metadata if present
                        if "<ADDITIONAL_METADATA>" in clean_prompt:
                            clean_prompt = clean_prompt.split("<ADDITIONAL_METADATA>")[0].strip()
                        table.add_row(created_at, "[bold cyan]User[/bold cyan]", clean_prompt[:90] + ("..." if len(clean_prompt) > 90 else ""))
                    elif data.get("tool_calls"):
                        for tc in data.get("tool_calls", []):
                            table.add_row(created_at, "[bold yellow]Tool[/bold yellow]", f"⚡ {tc.get('name')}")
        except Exception:
            continue

    console.print(table)
    console.print(f"\n[dim]Full raw transcripts are stored in: {BRAIN_DIR}/<session-id>/[/dim]\n")

if __name__ == "__main__":
    main()
