import asyncio
import os
import sys
import time
import shutil
from google.antigravity import Agent, LiteRTAgentConfig, types
from google.antigravity.hooks import hooks, policy
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel

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

async def main():
    if not os.path.exists(MODEL_PATH):
        console.print(f"[bold red][!] Model not found at: {MODEL_PATH}[/bold red]")
        return

    banner_text = (
        f"[bold cyan]Model:[/bold cyan] {MODEL_PATH}\n"
        f"[bold cyan]Workspace:[/bold cyan] {WORKSPACE}\n"
        f"[bold cyan]Engine:[/bold cyan] LiteRT on Apple Silicon Metal GPU ([bold green]100% Offline[/bold green])\n"
        f"[bold cyan]Navigation:[/bold cyan] Arrow keys (←/→ navigate cursor, ↑/↓ prompt history)\n"
        f"[bold cyan]Commands:[/bold cyan] Type [bold yellow]/exit[/bold yellow] to quit | [bold yellow]/clear[/bold yellow] to reset | [bold yellow]/history[/bold yellow] to view history"
    )
    console.print(Panel(banner_text, title="[bold yellow]Gemma 4 26B Local Agent (Antigravity + LiteRT)[/bold yellow]", border_style="yellow"))

    console.print("\n[dim]Loading model weights into unified memory...[/dim]")

    config = LiteRTAgentConfig(
        model_path=MODEL_PATH,
        workspaces=[WORKSPACE],
        policies=[policy.allow_all()],  # Allows autonomous tool execution
        hooks=[on_pre_tool, on_post_tool],  # Real-time tool lifecycle display
    )

    prompt_session = PromptSession(
        history=FileHistory(os.path.expanduser("~/.gemma_prompt_history.txt"))
    )
    prompt_style = Style.from_dict({
        "prompt": "ansicyan bold",
        "": "ansicyan",
    })

    async with Agent(config) as agent:
        console.print("[bold green]✓ Gemma 4 online & ready! Type your prompt below.[/bold green]\n")
        
        while True:
            try:
                user_prompt = await prompt_session.prompt_async(
                    [("class:prompt", "You > ")],
                    style=prompt_style,
                )
                user_prompt = user_prompt.strip()

                if not user_prompt:
                    continue
                if user_prompt.lower() in ("/exit", "/quit", "exit", "quit"):
                    console.print("\n[bold yellow]Shutting down local agent. See you next time![/bold yellow]")
                    break
                if user_prompt.lower() == "/clear":
                    console.print("\n[bold yellow][Conversation reset][/bold yellow]\n")
                    continue
                if user_prompt.lower() == "/history":
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
                async for token in response:
                    streamer.feed(token)
                streamer.flush()

                elapsed = time.time() - start_time
                console.print(f"\n[dim gray]⏱ Worked for {elapsed:.1f}s[/dim gray]\n")

            except (KeyboardInterrupt, EOFError):
                console.print("\n\n[bold yellow]Session terminated.[/bold yellow]")
                break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
