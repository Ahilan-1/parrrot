"""
Parrrot — CLI entry point (Typer)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="parrrot",
    help="Your private Jarvis. Runs on your machine. Does anything.",
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode="rich",
)
console = Console()

_DAEMON_PID_FILE = Path.home() / ".parrrot" / "daemon.pid"
_STATUS_FILE = Path.home() / ".parrrot" / "status.json"


# ---------------------------------------------------------------------------
# Default entry: onboarding or chat
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    Run Parrrot. First run triggers the setup wizard.
    After setup, opens the chat interface.
    """
    if ctx.invoked_subcommand is not None:
        return  # A subcommand was invoked — don't also run this

    from parrrot import config as cfg

    if cfg.is_first_run():
        try:
            from parrrot.onboarding import run_onboarding
            final_config = run_onboarding()
            if final_config.get("_start_now"):
                _start_daemon()
            else:
                console.print()
                console.print(
                    "  Run [bold cyan]parrrot chat[/bold cyan] to start talking!\n"
                )
        except ImportError as e:
            console.print(f"[red]Import error during onboarding: {e}[/red]")
            console.print("Try: pip install parrrot[all]")
            raise typer.Exit(1)
    else:
        asyncio.run(_chat_async())


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

@app.command()
def chat() -> None:
    """Start an interactive chat session."""
    asyncio.run(_chat_async())


async def _chat_async() -> None:
    from parrrot.ui.chat import run_chat
    try:
        await run_chat()
    except KeyboardInterrupt:
        console.print("\n[dim]Chat ended.[/dim]")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@app.command()
def run(
    task: str = typer.Argument(..., help="Task to execute"),
) -> None:
    """Run a one-off task and print the result."""
    asyncio.run(_run_task(task))


async def _run_task(task: str) -> None:
    from parrrot.core.agent import Agent
    from parrrot import config as cfg

    conf = cfg.load()
    name = conf["identity"].get("name", "Parrrot")
    console.print(f"\n[bold cyan]{name}[/bold cyan]: working on it...\n")

    agent = Agent()
    try:
        result = await agent.run_task(task)
        console.print(result)
    except Exception as e:
        _nice_error(str(e))


# ---------------------------------------------------------------------------
# daemon
# ---------------------------------------------------------------------------

@app.command()
def daemon() -> None:
    """Start Parrrot in background autonomous mode."""
    _start_daemon()


def _start_daemon() -> None:
    if _DAEMON_PID_FILE.exists():
        console.print("[yellow]Parrrot daemon is already running.[/yellow]")
        console.print("To stop it: [bold cyan]parrrot stop[/bold cyan]")
        return

    console.print("[cyan]Starting Parrrot daemon...[/cyan]")
    asyncio.run(_run_daemon())


async def _run_daemon() -> None:
    from parrrot.core.agent import Agent
    from parrrot.core.scheduler import Scheduler
    from parrrot.skills.loader import load_all_skills
    from parrrot import config as cfg

    conf = cfg.load()
    name = conf["identity"].get("name", "Parrrot")

    # Write PID file
    _DAEMON_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DAEMON_PID_FILE.write_text(str(os.getpid()))

    console.print(f"[green]{name} daemon started (PID {os.getpid()})[/green]")
    console.print(f"Stop with: [bold cyan]parrrot stop[/bold cyan]")

    agent = Agent()
    scheduler = Scheduler()
    scheduler.set_agent(agent)

    # Load skills
    skills = load_all_skills(scheduler, agent)
    if skills:
        console.print(f"[dim]Loaded {len(skills)} skill(s)[/dim]")

    scheduler.start()

    # Write status file
    def _write_status() -> None:
        jobs = scheduler.list_jobs()
        _STATUS_FILE.write_text(json.dumps({"jobs": jobs, "pid": os.getpid()}))

    _write_status()

    # Register global hotkey (Win+Shift+P) if keyboard is available
    _hotkey_registered = False
    try:
        import keyboard as _kb
        import subprocess, platform as _pl

        _HOTKEY_BIND = "win+shift+p"

        def _on_global_hotkey():
            if _pl.system() == "Windows":
                try:
                    import pyautogui
                    wins = pyautogui.getWindowsWithTitle("parrrot")
                    if wins:
                        wins[0].activate()
                        return
                except Exception:
                    pass
                subprocess.Popen(
                    ["cmd", "/k", "parrrot chat"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            elif _pl.system() == "Darwin":
                subprocess.Popen(
                    ["osascript", "-e",
                     'tell app "Terminal" to do script "parrrot chat"'],
                )
            else:
                for term in ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"]:
                    try:
                        subprocess.Popen([term, "--", "bash", "-c", "parrrot chat; bash"])
                        break
                    except FileNotFoundError:
                        continue

        _kb.add_hotkey(_HOTKEY_BIND, _on_global_hotkey)
        _hotkey_registered = True
        console.print(f"[dim]Global hotkey active: [bold]{_HOTKEY_BIND}[/bold] → open Parrrot anywhere[/dim]")
    except ImportError:
        console.print(
            "[dim]Tip: install [bold]keyboard[/bold] (pip install keyboard) "
            "to enable the Win+Shift+P global hotkey.[/dim]"
        )

    # Handle termination gracefully
    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    console.print(f"[dim]{name} is watching over your computer. Press Ctrl+C to stop.[/dim]")

    try:
        await stop_event.wait()
    finally:
        if _hotkey_registered:
            try:
                _kb.remove_hotkey(_HOTKEY_BIND)
            except Exception:
                pass
        scheduler.stop()
        _DAEMON_PID_FILE.unlink(missing_ok=True)
        _STATUS_FILE.unlink(missing_ok=True)
        console.print(f"\n[yellow]{name} daemon stopped.[/yellow]")


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

@app.command()
def stop() -> None:
    """Stop the background daemon."""
    if not _DAEMON_PID_FILE.exists():
        console.print("[yellow]Parrrot daemon is not running.[/yellow]")
        return
    try:
        pid = int(_DAEMON_PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Stopped Parrrot daemon (PID {pid})[/green]")
    except (ProcessLookupError, ValueError):
        console.print("[yellow]Daemon process not found. Cleaning up...[/yellow]")
        _DAEMON_PID_FILE.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[red]Error stopping daemon: {e}[/red]")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status() -> None:
    """Show Parrrot's current status."""
    from parrrot.ui.dashboard import show_status
    show_status()


# ---------------------------------------------------------------------------
# memory commands
# ---------------------------------------------------------------------------

memory_app = typer.Typer(help="Manage Parrrot's memory", no_args_is_help=False)
app.add_typer(memory_app, name="memory")


@memory_app.callback(invoke_without_command=True)
def memory_main(
    ctx: typer.Context,
    query: Optional[str] = typer.Argument(None, help="Search query"),
) -> None:
    """Browse or search Parrrot's memory."""
    if ctx.invoked_subcommand is not None:
        return
    from parrrot.core import memory as mem
    if query:
        results = mem.recall(query)
        if results:
            for r in results:
                console.print(f"[cyan]{r['key']}[/cyan] [{r['category']}]: {r['value']}")
        else:
            console.print(f"[dim]No memories matching '{query}'[/dim]")
    else:
        facts = mem.all_facts()
        if not facts:
            console.print("[dim]No memories yet.[/dim]")
            return
        counts = mem.count()
        console.print(f"[bold]Memory:[/bold] {counts['facts']} facts, {counts['events']} events, {counts['tasks']} tasks\n")
        for k, v in list(facts.items())[:30]:
            console.print(f"  [cyan]{k}[/cyan]: {v}")


@memory_app.command("forget")
def memory_forget(key: str = typer.Argument(..., help="Memory key to delete")) -> None:
    """Delete a memory entry."""
    from parrrot.core import memory as mem
    if mem.forget(key):
        console.print(f"[green]Forgot: {key}[/green]")
    else:
        console.print(f"[yellow]No memory found with key: {key}[/yellow]")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@app.command()
def config() -> None:
    """Open the config file for editing."""
    from parrrot import config as cfg
    path = cfg.CONFIG_PATH
    if not path.exists():
        console.print("[yellow]No config file yet. Run 'parrrot' to set up first.[/yellow]")
        return
    console.print(f"Config file: [bold]{path}[/bold]")

    # Try to open in default editor
    import subprocess
    editor = os.environ.get("EDITOR", "")
    if editor:
        subprocess.run([editor, str(path)])
    elif sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------

skills_app = typer.Typer(help="Manage Parrrot skills", no_args_is_help=False)
app.add_typer(skills_app, name="skills")


@skills_app.callback(invoke_without_command=True)
def skills_main(ctx: typer.Context) -> None:
    """List installed skills."""
    if ctx.invoked_subcommand is not None:
        return
    from parrrot.skills.loader import list_skills
    skills = list_skills()
    if not skills:
        console.print("[dim]No skills installed. Drop .py files into ~/.parrrot/skills/[/dim]")
        return
    console.print(f"\n[bold]Installed skills ({len(skills)}):[/bold]\n")
    for s in skills:
        sched = f"  [dim]cron: {s['schedule']}[/dim]" if s["schedule"] else ""
        console.print(f"  [bold cyan]{s['name']}[/bold cyan]{sched}")
        console.print(f"    [dim]{s['description']}[/dim]")
    console.print()


@skills_app.command("add")
def skills_add(
    file: str = typer.Argument(..., help="Path to skill .py file"),
) -> None:
    """Install a skill by copying it to ~/.parrrot/skills/."""
    import shutil
    src = Path(file)
    if not src.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
    dest = Path.home() / ".parrrot" / "skills" / src.name
    shutil.copy(src, dest)
    console.print(f"[green]Skill installed: {src.name}[/green]")
    console.print(f"Restart the daemon to activate: [bold cyan]parrrot daemon[/bold cyan]")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@app.command()
def update() -> None:
    """Update Parrrot to the latest version."""
    import subprocess
    console.print("[cyan]Updating Parrrot...[/cyan]")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "parrrot"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print("[green]Parrrot updated successfully![/green]")
    else:
        console.print(f"[red]Update failed:[/red]\n{result.stderr}")


# ---------------------------------------------------------------------------
# hotkey — global Win+Shift+P to invoke Parrrot from anywhere
# ---------------------------------------------------------------------------

@app.command()
def hotkey(
    bind: str = typer.Option(
        "win+shift+p",
        help="Key combination to register (default: win+shift+p)",
    ),
    unregister: bool = typer.Option(False, "--off", help="Remove the global hotkey"),
) -> None:
    """
    Register a system-wide hotkey (default Win+Shift+P) that opens or focuses
    the Parrrot chat window from anywhere on your PC.

    Requires: pip install keyboard
    Run 'parrrot daemon' to activate hotkey in background.
    """
    try:
        import keyboard as _kb
    except ImportError:
        console.print(
            Panel(
                "Global hotkey requires the [bold]keyboard[/bold] package.\n\n"
                "Install it with:\n"
                "  [bold cyan]pip install keyboard[/bold cyan]\n\n"
                "Then run [bold cyan]parrrot daemon[/bold cyan] to keep the hotkey active.",
                title="Missing dependency",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    if unregister:
        try:
            _kb.remove_hotkey(bind)
            console.print(f"[yellow]Global hotkey removed: {bind}[/yellow]")
        except Exception:
            console.print(f"[dim]No active hotkey for: {bind}[/dim]")
        return

    console.print(f"[cyan]Registering global hotkey: [bold]{bind}[/bold][/cyan]")
    console.print("Press [bold cyan]Ctrl+C[/bold cyan] to stop (or use 'parrrot daemon' to keep it running in background).\n")

    def _on_hotkey():
        """Bring the Parrrot terminal to front, or open a new chat window."""
        import subprocess, platform as _pl
        if _pl.system() == "Windows":
            # Try to focus existing terminal with Parrrot in the title
            try:
                import pyautogui
                wins = pyautogui.getWindowsWithTitle("parrrot")
                if wins:
                    wins[0].activate()
                    return
            except Exception:
                pass
            # Open a new terminal with parrrot chat
            subprocess.Popen(
                ["cmd", "/k", "parrrot chat"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        elif _pl.system() == "Darwin":
            subprocess.Popen(
                ["osascript", "-e",
                 'tell app "Terminal" to do script "parrrot chat"'],
            )
        else:
            for term in ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"]:
                try:
                    subprocess.Popen([term, "--", "bash", "-c", "parrrot chat; bash"])
                    break
                except FileNotFoundError:
                    continue

    _kb.add_hotkey(bind, _on_hotkey)
    console.print(f"[green]✓ Hotkey active: press [bold]{bind}[/bold] anywhere to invoke Parrrot[/green]")

    try:
        _kb.wait()  # blocks until KeyboardInterrupt
    except KeyboardInterrupt:
        _kb.remove_hotkey(bind)
        console.print("\n[yellow]Hotkey deactivated.[/yellow]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nice_error(error: str) -> None:
    if "connection" in error.lower() or "refused" in error.lower():
        msg = (
            "Can't reach the AI model.\n\n"
            "If using Ollama: [bold]ollama serve[/bold]\n"
            "Then check: [bold]ollama list[/bold]"
        )
    elif "not found" in error.lower() and "model" in error.lower():
        msg = "Model not found. Pull it with: [bold]ollama pull <model>[/bold]"
    else:
        msg = f"Error: {error}"
    console.print(Panel(msg, title="[bold red]Something went wrong[/bold red]", border_style="red"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_app() -> None:
    app()


if __name__ == "__main__":
    run_app()
