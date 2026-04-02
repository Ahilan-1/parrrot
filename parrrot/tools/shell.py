"""
Parrrot — Shell execution tools
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Optional

import psutil

from parrrot.tools.registry import registry


def _run_command(cmd: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Run a shell command, return combined stdout/stderr."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts: list[str] = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr] {err}")
        if not parts:
            return f"(exit code {result.returncode})"
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error running command: {e}"


def _run_script(script_path: str) -> str:
    """Run a Python or shell script file."""
    p = os.path.expanduser(script_path)
    if not os.path.exists(p):
        return f"Script not found: {p}"
    if p.endswith(".py"):
        return _run_command(f"{sys.executable} {p}", timeout=120)
    else:
        return _run_command(p, timeout=120)


def _install_package(package_name: str) -> str:
    """Install a Python package via pip."""
    return _run_command(f"{sys.executable} -m pip install {package_name}", timeout=120)


def _get_running_processes(filter: Optional[str] = None) -> str:
    """List running processes, optionally filtered by name."""
    procs: list[str] = []
    for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_percent"]):
        try:
            name = proc.info["name"] or ""
            if filter and filter.lower() not in name.lower():
                continue
            procs.append(
                f"[{proc.info['pid']:>6}] {name:<30} "
                f"cpu:{proc.info['cpu_percent']:.1f}%  "
                f"mem:{proc.info['memory_percent']:.1f}%"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if not procs:
        return "No processes found."
    return "\n".join(procs[:50])


def _kill_process(name_or_pid: str) -> str:
    """Kill a process by name or PID."""
    # Try PID first
    try:
        pid = int(name_or_pid)
        proc = psutil.Process(pid)
        proc.terminate()
        return f"Terminated process {pid} ({proc.name()})"
    except (ValueError, psutil.NoSuchProcess):
        pass

    # Try name
    killed = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if name_or_pid.lower() in (proc.info["name"] or "").lower():
                proc.terminate()
                killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        return f"Terminated: {', '.join(killed)}"
    return f"No process found matching '{name_or_pid}'"


def _open_application(app_name: str) -> str:
    """Open an application by name."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(app_name)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen([app_name])
        return f"Opened: {app_name}"
    except Exception as e:
        return f"Could not open '{app_name}': {e}"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "run_command",
    "Run a shell command and return its output",
    {"cmd": "command to run", "timeout": "seconds to wait (default 30)", "cwd": "working directory"},
    requires_confirm=True,
)(_run_command)

registry.register(
    "run_script",
    "Run a Python or shell script file",
    {"script_path": "path to the script"},
    requires_confirm=True,
)(_run_script)

registry.register(
    "install_package",
    "Install a Python package via pip",
    {"package_name": "package name, e.g. 'requests' or 'requests==2.31'"},
)(_install_package)

registry.register(
    "get_running_processes",
    "List currently running processes",
    {"filter": "optional name filter"},
)(_get_running_processes)

registry.register(
    "kill_process",
    "Kill a process by name or PID",
    {"name_or_pid": "process name or numeric PID"},
    requires_confirm=True,
)(_kill_process)

registry.register(
    "open_application",
    "Open an application",
    {"app_name": "application name or path"},
)(_open_application)
