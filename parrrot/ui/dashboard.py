"""
Parrrot — Rich status dashboard
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import datetime
import os
import platform
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from parrrot import config as cfg
from parrrot.core import memory

console = Console()

_DAEMON_PID_FILE = Path.home() / ".parrrot" / "daemon.pid"


def _is_daemon_running() -> tuple[bool, int | None]:
    if not _DAEMON_PID_FILE.exists():
        return False, None
    try:
        pid = int(_DAEMON_PID_FILE.read_text().strip())
        import psutil
        if psutil.pid_exists(pid):
            return True, pid
        _DAEMON_PID_FILE.unlink(missing_ok=True)
        return False, None
    except Exception:
        return False, None


def show_status() -> None:
    conf = cfg.load()
    name = conf["identity"].get("name", "Parrrot")
    mode = conf["model"]["mode"]
    local_model = conf["model"].get("local_model", "N/A")
    cloud_model = conf["model"].get("cloud_model", "N/A")
    cloud_provider = conf["model"].get("cloud_provider", "")

    model_label = {
        "local": f"{local_model} (Ollama local)",
        "cloud": f"{cloud_model} via {cloud_provider}",
        "hybrid": f"{local_model} (local) + {cloud_model} ({cloud_provider})",
    }.get(mode, mode)

    is_running, pid = _is_daemon_running()
    status_str = f"[green]Running[/green] (daemon PID {pid})" if is_running else "[yellow]Stopped[/yellow]"

    mem_counts = memory.count()

    # Main table
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold cyan", width=12)
    table.add_column("Value", style="white")

    table.add_row("Status", status_str)
    table.add_row("Model", model_label)
    table.add_row("Memory", f"{mem_counts['facts']} facts  ·  {mem_counts['events']} events  ·  {mem_counts['tasks']} tasks")
    table.add_row("Config", str(Path.home() / ".parrrot" / "config.toml"))
    table.add_row("OS", f"{platform.system()} {platform.release()}")

    # Scheduled tasks (if scheduler available)
    sched_info = _get_sched_info()

    content = table
    if sched_info:
        from rich.console import Group
        content = Group(table, sched_info)

    console.print()
    console.print(
        Panel(
            content,
            title=f"[bold green]{name} Status[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def _get_sched_info():
    """Try to get scheduled jobs from the daemon (via a status file)."""
    status_path = Path.home() / ".parrrot" / "status.json"
    if not status_path.exists():
        return None

    try:
        import json
        data = json.loads(status_path.read_text())
        jobs = data.get("jobs", [])
        if not jobs:
            return None

        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("Task", style="bold")
        table.add_column("Next run", style="dim")
        for job in jobs[:10]:
            table.add_row(job.get("name", "?"), job.get("next_run", "N/A"))
        return table
    except Exception:
        return None
