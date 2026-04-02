"""
Parrrot — First-run interactive setup wizard
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# ASCII art
# ---------------------------------------------------------------------------

PARROT_ART = r"""
[bold green]        ___
       /   \
      | o o |  [bold yellow]PARRROT[/bold yellow]
      |  ^  |
     /| \_/ |\
    / |  _  | \
   /  | | | |  \
  /   |_| |_|   \
 /_______________\
[/bold green]
"""

PARROT_ART_FULL = r"""[bold green]
         ,_
        /( )-,
       / /    \
      | |  o o |   [bold white]P A R R R O T[/bold white]
      | |   ^  |   [dim]Your private Jarvis.[/dim]
       \ \  w  |   [dim]Runs on your machine.[/dim]
        `.\___/    [dim]Does anything.[/dim]
          |  |
         /|  |\
        / |  | \
[/bold green]"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pause(msg: str = "Press [bold cyan]Enter[/bold cyan] to continue...") -> None:
    console.print()
    Prompt.ask(f"  {msg}", default="", show_default=False)


def _step_header(step: int, total: int, title: str) -> None:
    console.print()
    console.rule(
        f"[bold cyan]Step {step}/{total}[/bold cyan]  [white]{title}[/white]",
        style="cyan",
    )
    console.print()


def _success(msg: str) -> None:
    console.print(f"  [bold green]✓[/bold green]  {msg}")


def _info(msg: str) -> None:
    console.print(f"  [bold blue]→[/bold blue]  {msg}")


def _warn(msg: str) -> None:
    console.print(f"  [bold yellow]![/bold yellow]  {msg}")


def _error(msg: str) -> None:
    console.print(f"  [bold red]✗[/bold red]  {msg}")


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------


def _is_ollama_running() -> bool:
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _list_ollama_models() -> list[str]:
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _is_ollama_installed() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _offer_ollama_start() -> bool:
    """Try to start Ollama if installed but not running."""
    if not _is_ollama_installed():
        return False
    console.print()
    _warn("Ollama is installed but not running.")
    start = Confirm.ask("  Start Ollama now?", default=True)
    if not start:
        return False
    try:
        if platform.system() == "Windows":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,  # type: ignore[attr-defined]
            )
        else:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with Progress(
            SpinnerColumn(),
            TextColumn("[cyan]Starting Ollama..."),
            transient=True,
        ) as prog:
            prog.add_task("wait", total=None)
            for _ in range(15):
                time.sleep(1)
                if _is_ollama_running():
                    break
        if _is_ollama_running():
            _success("Ollama started successfully!")
            return True
        else:
            _error("Ollama didn't start in time. Start it manually: [bold]ollama serve[/bold]")
            return False
    except Exception as exc:
        _error(f"Could not start Ollama: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 1 — Welcome
# ---------------------------------------------------------------------------


def _step_welcome() -> None:
    console.clear()
    console.print()
    console.print(Align.center(PARROT_ART_FULL))
    console.print(
        Align.center(
            Panel.fit(
                "[bold white]Welcome to Parrrot Setup![/bold white]\n\n"
                "[dim]This wizard will configure your personal AI assistant.\n"
                "It takes about 2 minutes and you won't need to edit any files.[/dim]",
                border_style="cyan",
                padding=(1, 4),
            )
        )
    )
    _pause()


# ---------------------------------------------------------------------------
# Step 2 — Model selection
# ---------------------------------------------------------------------------


def _pick_local_model() -> dict[str, str]:
    """Returns dict with local_model and local_url."""
    console.print()
    console.print("  [bold]Local Ollama model[/bold]")
    console.print()

    if not _is_ollama_running():
        if not _offer_ollama_start():
            # Ollama not available — offer manual entry
            _warn("You can set the model later in [bold]~/.parrrot/config.toml[/bold]")
            model = Prompt.ask(
                "  Type a model name to use when Ollama is running",
                default="llama3.2",
            )
            return {"local_model": model, "local_url": "http://localhost:11434"}

    models = _list_ollama_models()
    suggested = ["llama3.2", "mistral", "phi3", "gemma2", "qwen2.5", "deepseek-r1"]

    if models:
        console.print("  [bold]Models installed on this machine:[/bold]")
        console.print()
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Num", style="bold cyan", width=4)
        table.add_column("Model", style="white")
        for i, m in enumerate(models, 1):
            table.add_row(f"[{i}]", m)
        table.add_row("[+]", "[dim]Type a custom model name[/dim]")
        console.print(table)
        console.print()

        while True:
            choice = Prompt.ask("  Pick a model", default="1")
            if choice == "+":
                model = Prompt.ask("  Model name")
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    model = models[idx]
                    break
                _error("Invalid choice, try again.")
            except ValueError:
                # They typed a model name directly
                model = choice
                break
    else:
        console.print("  [bold]No models installed yet.[/bold] Popular options:")
        console.print()
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Num", style="bold cyan", width=4)
        table.add_column("Model", style="white")
        table.add_column("Notes", style="dim")
        notes = {
            "llama3.2": "Best all-around (recommended)",
            "mistral": "Fast, great for coding",
            "phi3": "Tiny, runs on anything",
            "gemma2": "Google's model",
            "qwen2.5": "Multilingual",
        }
        for i, m in enumerate(suggested, 1):
            table.add_row(f"[{i}]", m, notes.get(m, ""))
        console.print(table)
        console.print()

        while True:
            choice = Prompt.ask("  Pick a model (or type any name)", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(suggested):
                    model = suggested[idx]
                    break
                _error("Invalid choice, try again.")
            except ValueError:
                model = choice
                break

        console.print()
        _info(f"Will pull [bold cyan]{model}[/bold cyan] from Ollama on first use.")
        _info("Run [bold]ollama pull " + model + "[/bold] to download it now.")

    _success(f"Local model: [bold cyan]{model}[/bold cyan]")
    return {"local_model": model, "local_url": "http://localhost:11434"}


def _pick_cloud_model(secrets: dict[str, str]) -> dict[str, str]:
    """Returns dict with cloud_provider, cloud_model."""
    providers = {
        "a": ("openai", "OpenAI", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]),
        "b": ("anthropic", "Anthropic Claude", ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6"]),
        "c": ("google", "Google Gemini", ["gemini-1.5-pro", "gemini-1.5-flash"]),
        "d": ("groq", "Groq (fast + free tier)", ["llama3-70b-8192", "mixtral-8x7b-32768"]),
        "e": ("custom", "Custom endpoint", []),
    }

    console.print()
    console.print("  [bold]Choose cloud provider:[/bold]")
    console.print()
    for key, (_, name, models) in providers.items():
        first = models[0] if models else "custom"
        console.print(f"  [[bold cyan]{key}[/bold cyan]] {name}  [dim]({first})[/dim]")
    console.print()

    while True:
        choice = Prompt.ask("  Provider", default="a").lower().strip()
        if choice in providers:
            break
        _error("Type one of: a, b, c, d, e")

    provider_key, provider_name, model_list = providers[choice]

    if provider_key == "custom":
        endpoint = Prompt.ask("  API endpoint URL (OpenAI-compatible)")
        model = Prompt.ask("  Model name")
        api_key = Prompt.ask("  API key", password=True)
        secrets[f"{provider_key}_api_key"] = api_key
        return {"cloud_provider": "custom", "cloud_model": model, "cloud_endpoint": endpoint}

    # Show model list
    console.print()
    console.print(f"  [bold]{provider_name} models:[/bold]")
    for i, m in enumerate(model_list, 1):
        console.print(f"  [[bold cyan]{i}[/bold cyan]] {m}")
    console.print(f"  [[bold cyan]+[/bold cyan]] Custom model name")
    console.print()

    while True:
        choice2 = Prompt.ask("  Pick a model", default="1")
        if choice2 == "+":
            model = Prompt.ask("  Model name")
            break
        try:
            idx = int(choice2) - 1
            if 0 <= idx < len(model_list):
                model = model_list[idx]
                break
            _error("Invalid choice.")
        except ValueError:
            model = choice2
            break

    api_key = Prompt.ask(f"  {provider_name} API key", password=True)
    secrets[f"{provider_key}_api_key"] = api_key

    _success(f"Cloud model: [bold cyan]{model}[/bold cyan] via {provider_name}")
    return {"cloud_provider": provider_key, "cloud_model": model}


def _step_model(config: dict[str, Any], secrets: dict[str, str]) -> None:
    _step_header(2, 6, "Choose your AI brain")

    console.print("  Where should Parrrot's brain live?\n")
    console.print("  [[bold cyan]1[/bold cyan]] [bold]Local only[/bold]  [dim](100% private, no internet needed)[/dim]")
    console.print("  [[bold cyan]2[/bold cyan]] [bold]Cloud[/bold]     [dim](OpenAI, Anthropic, Groq, etc.)[/dim]")
    console.print("  [[bold cyan]3[/bold cyan]] [bold]Hybrid[/bold]    [dim](local for private, cloud for heavy tasks)[/dim]")
    console.print()

    while True:
        choice = Prompt.ask("  Choice", default="1")
        if choice in ("1", "2", "3"):
            break
        _error("Type 1, 2, or 3")

    if choice == "1":
        config["model"]["mode"] = "local"
        local = _pick_local_model()
        config["model"].update(local)

    elif choice == "2":
        config["model"]["mode"] = "cloud"
        cloud = _pick_cloud_model(secrets)
        config["model"].update(cloud)

    else:  # hybrid
        config["model"]["mode"] = "hybrid"
        console.print()
        console.print("  [bold]Local model (for private/quick tasks):[/bold]")
        local = _pick_local_model()
        config["model"].update(local)
        console.print()
        console.print("  [bold]Cloud model (for heavy/complex tasks):[/bold]")
        cloud = _pick_cloud_model(secrets)
        config["model"].update(cloud)

        console.print()
        console.print("  When should I use the cloud model?\n")
        console.print("  [[bold cyan]a[/bold cyan]] Never (local always)")
        console.print("  [[bold cyan]b[/bold cyan]] Only when you ask me to")
        console.print("  [[bold cyan]c[/bold cyan]] Auto (I decide based on task complexity)")
        console.print()
        threshold = Prompt.ask("  Choice", default="c").lower()
        config["model"]["hybrid_threshold"] = {"a": "never", "b": "manual", "c": "auto"}.get(
            threshold, "auto"
        )


# ---------------------------------------------------------------------------
# Step 3 — Permissions
# ---------------------------------------------------------------------------


def _step_permissions(config: dict[str, Any]) -> None:
    _step_header(3, 6, "Permissions")

    console.print(
        "  Parrrot needs certain permissions to act as your Jarvis.\n"
        "  You can change these any time in [bold]~/.parrrot/config.toml[/bold]\n"
    )

    perms = [
        ("file_access", "Read and write files on your computer", True, "required"),
        ("shell_access", "Run terminal commands", True, "required"),
        ("mouse_keyboard", "Control your mouse and keyboard", True, "for PC automation"),
        ("screen_capture", "Take screenshots to see your screen", True, "for vision tasks"),
        ("browser_control", "Open and control your browser", True, "for web search"),
        ("notifications", "Send desktop notifications", True, "for reminders"),
        ("autostart", "Start automatically when your computer starts", False, "optional"),
    ]

    for key, description, default, note in perms:
        required = note == "required"
        label = f"  [white]{description}[/white] [dim]({note})[/dim]"
        console.print(label)
        if required:
            console.print("  [dim](This permission is required for Parrrot to work.)[/dim]")
            config["permissions"][key] = True
            _success("Granted")
        else:
            granted = Confirm.ask("  Grant this?", default=default)
            config["permissions"][key] = granted
            if granted:
                _success("Granted")
            else:
                _info("Skipped — you can enable this later")
        console.print()


# ---------------------------------------------------------------------------
# Step 4 — Name
# ---------------------------------------------------------------------------


def _step_name(config: dict[str, Any]) -> None:
    _step_header(4, 6, "Give Parrrot a name")

    console.print(
        "  What should I call myself?\n"
        "  [dim]Popular choices: Jarvis, Friday, Nova, Aria, Max — or keep Parrrot[/dim]\n"
    )
    name = Prompt.ask("  Name", default="Parrrot").strip()
    if not name:
        name = "Parrrot"
    config["identity"]["name"] = name

    console.print()
    user_name = Prompt.ask("  And what's your name?", default="").strip()
    if user_name:
        config["identity"]["user_name"] = user_name
    _success(f"Hello, [bold]{user_name or 'there'}[/bold]! I'll be your [bold cyan]{name}[/bold cyan].")


# ---------------------------------------------------------------------------
# Step 5 — Quick demo
# ---------------------------------------------------------------------------


def _run_demo(config: dict[str, Any]) -> None:
    _step_header(5, 6, "Quick demo")

    name = config["identity"].get("name", "Parrrot")
    console.print(f"  Let me show you what [bold cyan]{name}[/bold cyan] can do.\n")
    time.sleep(0.5)

    # Demo 1: Desktop scan
    _demo_desktop()

    # Demo 2: Web search hint
    _demo_web()

    # Demo 3: Memory
    user_name = config["identity"].get("user_name", "")
    if user_name:
        _demo_memory(user_name)


def _demo_desktop() -> None:
    from parrrot.tools.filesystem import get_desktop_contents  # lazy import

    console.print("  [bold]Checking your desktop...[/bold]")
    with Progress(SpinnerColumn(), TextColumn("[cyan]Scanning..."), transient=True) as p:
        p.add_task("s", total=None)
        time.sleep(0.8)
    try:
        items = get_desktop_contents()
        count = len(items)
        if count == 0:
            _info("Your desktop is clean — nothing to report!")
        else:
            _info(f"Found [bold]{count}[/bold] item(s) on your desktop.")
            for item in items[:5]:
                console.print(f"    [dim]• {item}[/dim]")
            if count > 5:
                console.print(f"    [dim]... and {count - 5} more[/dim]")
    except Exception as exc:
        _info(f"Desktop scan skipped: {exc}")
    console.print()


def _demo_web() -> None:
    console.print("  [bold]Web browsing:[/bold]")
    _info(
        "When you ask me to search the web, I'll open your browser, "
        "search, and read the results — just like a human would."
    )
    _info("Try: [bold cyan]parrrot chat[/bold cyan] → [italic]\"what's the weather today?\"[/italic]")
    console.print()


def _demo_memory(user_name: str) -> None:
    console.print("  [bold]Memory:[/bold]")
    _info(f"I've remembered your name: [bold]{user_name}[/bold]")
    _info("Everything I learn is stored locally in [bold]~/.parrrot/memory/[/bold]")
    _info("Nothing ever leaves your machine unless you ask me to search the web.")
    console.print()


# ---------------------------------------------------------------------------
# Step 6 — Done
# ---------------------------------------------------------------------------


def _step_done(config: dict[str, Any]) -> None:
    _step_header(6, 6, "All set!")

    name = config["identity"].get("name", "Parrrot")
    user_name = config["identity"].get("user_name", "")
    mode = config["model"]["mode"]
    model_label = {
        "local": config["model"].get("local_model", "local"),
        "cloud": f"{config['model'].get('cloud_provider', 'cloud')} / {config['model'].get('cloud_model', '')}",
        "hybrid": f"hybrid ({config['model'].get('local_model', 'local')} + cloud)",
    }.get(mode, mode)

    # Summary panel
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("Key", style="bold cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Name", name)
    if user_name:
        summary.add_row("User", user_name)
    summary.add_row("Model", model_label)
    summary.add_row("Config", str(Path.home() / ".parrrot" / "config.toml"))
    summary.add_row("Memory", str(Path.home() / ".parrrot" / "memory" / ""))

    console.print(
        Panel(
            summary,
            title=f"[bold green]{name} is ready![/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()

    # Command cheatsheet
    cheatsheet = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    cheatsheet.add_column("Command", style="bold cyan")
    cheatsheet.add_column("What it does", style="dim")
    cheatsheet.add_row("parrrot chat", "Start talking to " + name)
    cheatsheet.add_row('parrrot run "task"', "Do a one-off task and exit")
    cheatsheet.add_row("parrrot daemon", "Run in the background 24/7")
    cheatsheet.add_row("parrrot status", "See what " + name + " is doing")
    cheatsheet.add_row("parrrot memory", "Browse what I remember")
    cheatsheet.add_row("parrrot config", "Change settings")

    console.print(Panel(cheatsheet, title="[bold]Quick commands[/bold]", border_style="cyan"))
    console.print()

    start_now = Confirm.ask(
        f"  Start [bold cyan]{name}[/bold cyan] in the background now?", default=False
    )
    console.print()
    return start_now  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Secrets encryption
# ---------------------------------------------------------------------------


def _save_secrets(secrets: dict[str, str], parrrot_dir: Path) -> None:
    if not secrets:
        return
    secrets_path = parrrot_dir / "secrets.json"
    try:
        from cryptography.fernet import Fernet

        key_path = parrrot_dir / ".key"
        if key_path.exists():
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            key_path.chmod(0o600)

        fernet = Fernet(key)
        encrypted: dict[str, str] = {}
        for k, v in secrets.items():
            encrypted[k] = fernet.encrypt(v.encode()).decode()

        secrets_path.write_text(json.dumps(encrypted, indent=2))
        secrets_path.chmod(0o600)
        _success("API keys saved and encrypted.")
    except ImportError:
        # Fall back to plain JSON with warning
        secrets_path.write_text(json.dumps(secrets, indent=2))
        secrets_path.chmod(0o600)
        _warn("cryptography package not found — secrets saved as plain JSON. Install it: pip install cryptography")


# ---------------------------------------------------------------------------
# Config save
# ---------------------------------------------------------------------------


def _save_config(config: dict[str, Any], parrrot_dir: Path) -> None:
    import tomli_w

    config_path = parrrot_dir / "config.toml"
    config_path.write_bytes(tomli_w.dumps(config).encode())
    _success(f"Config saved to [bold]{config_path}[/bold]")


def _build_default_config() -> dict[str, Any]:
    return {
        "identity": {
            "name": "Parrrot",
            "user_name": "",
        },
        "model": {
            "mode": "local",
            "local_model": "llama3.2",
            "local_url": "http://localhost:11434",
            "cloud_provider": "",
            "cloud_model": "",
            "cloud_endpoint": "",
            "hybrid_threshold": "auto",
        },
        "permissions": {
            "file_access": True,
            "shell_access": True,
            "mouse_keyboard": True,
            "screen_capture": True,
            "browser_control": True,
            "notifications": True,
            "autostart": False,
        },
        "privacy": {
            "local_first": True,
            "log_conversations": False,
            "telemetry": False,
        },
        "scheduler": {
            "heartbeat_interval": 300,
            "enabled": True,
        },
        "ui": {
            "theme": "dark",
            "show_tool_calls": True,
            "compact_mode": False,
        },
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_onboarding() -> dict[str, Any]:
    """
    Run the full first-time setup wizard.
    Returns the final config dict (already saved to disk).
    """
    parrrot_dir = Path.home() / ".parrrot"
    parrrot_dir.mkdir(parents=True, exist_ok=True)
    (parrrot_dir / "memory").mkdir(exist_ok=True)
    (parrrot_dir / "skills").mkdir(exist_ok=True)
    (parrrot_dir / "logs").mkdir(exist_ok=True)

    config = _build_default_config()
    secrets: dict[str, str] = {}

    try:
        # Step 1 — Welcome
        _step_welcome()

        # Step 2 — Model
        _step_model(config, secrets)

        # Step 3 — Permissions
        _step_permissions(config)

        # Step 4 — Name
        _step_name(config)

        # Step 5 — Demo
        _run_demo(config)

        # Save config + secrets before step 6
        _save_config(config, parrrot_dir)
        _save_secrets(secrets, parrrot_dir)

        # Step 6 — Done (returns bool: start now?)
        start_now = _step_done(config)

    except KeyboardInterrupt:
        console.print()
        console.print("[bold yellow]Setup interrupted.[/bold yellow]")
        console.print(
            "Run [bold cyan]parrrot[/bold cyan] again to complete setup, "
            "or edit [bold]~/.parrrot/config.toml[/bold] manually."
        )
        # Save whatever we have so far
        try:
            _save_config(config, parrrot_dir)
        except Exception:
            pass
        sys.exit(0)

    config["_start_now"] = start_now  # type: ignore[assignment]
    return config
