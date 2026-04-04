"""
Parrrot — Rich interactive chat interface with prompt_toolkit navigation.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

from parrrot import config as cfg
from parrrot.core import memory

console = Console()

# Persistent history file
_HISTORY_FILE = Path.home() / ".parrrot" / "history"

# Fun verbs for the thinking status — shown while the agent is running
_THINKING_VERBS = [
    "cooking",
    "brewing",
    "crafting",
    "conjuring",
    "wiring",
    "crunching",
    "plotting",
    "scheming",
    "assembling",
    "forging",
    "baking",
    "distilling",
    "engineering",
    "summoning",
    "weaving",
    "manifesting",
    "computing",
]

# Buffer for tool events — filled during agent run, printed after answer if verbose
_tool_event_buffer: list[tuple[str, str, object]] = []

# All slash commands available in chat
_SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/new",
    "/reset",
    "/status",
    "/memory",
    "/tools",
    "/model",
    "/verbose",
    "/v",
    "/compact",
    "/history",
    "/hotkey",
    "/exit",
    "/quit",
]


def _header(conf: dict) -> Panel:
    name = conf["identity"].get("name", "Parrrot")
    mode = conf["model"]["mode"]
    model = conf["model"].get("local_model" if mode == "local" else "cloud_model", "?")
    mem_counts = memory.count()
    total_mem = sum(mem_counts.values())

    info = (
        f"[bold cyan]{name}[/bold cyan]  "
        f"[dim]│[/dim]  Model: [green]{model}[/green] ({mode})  "
        f"[dim]│[/dim]  Memory: [yellow]{total_mem}[/yellow] entries  "
        f"[dim]│[/dim]  [dim]↑↓ history · Tab complete · Ctrl+R search · /help[/dim]"
    )
    return Panel(info, box=box.ROUNDED, border_style="cyan", padding=(0, 1))


def _make_prompt_session(conf: dict):
    """Build a prompt_toolkit PromptSession with history, completion, key bindings."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style
        from prompt_toolkit.formatted_text import HTML

        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Tab-complete slash commands + common task starters
        completer = WordCompleter(
            _SLASH_COMMANDS + [
                "open", "close", "launch", "search", "find", "move",
                "copy", "delete", "create", "list", "show", "screenshot",
                "click", "type", "scroll", "navigate",
            ],
            sentence=True,
            ignore_case=True,
            pattern=r"(?:[^\s]|\s(?!\s))*",
        )

        kb = KeyBindings()

        @kb.add("c-l")
        def _clear_screen(event):
            """Ctrl+L — clear terminal."""
            event.app.renderer.reset()
            event.app.output.erase_screen()
            # reprint header
            conf_now = cfg.load()
            console.print(_header(conf_now))

        name = conf["identity"].get("name", "Parrrot")
        mode = conf["model"]["mode"]
        model_str = conf["model"].get(
            "local_model" if mode == "local" else "cloud_model", "?"
        )

        def _toolbar():
            return HTML(
                f" <b>{name}</b> · <ansigreen>{model_str}</ansigreen> ({mode})"
                " · <ansicyan>Tab</ansicyan> complete"
                " · <ansicyan>↑↓</ansicyan> history"
                " · <ansicyan>Ctrl+R</ansicyan> search"
                " · <ansicyan>/help</ansicyan> commands"
            )

        style = Style.from_dict(
            {
                "prompt": "bold ansiwhite",
                "bottom-toolbar": "bg:#1a1a2e #6c6c8a",
            }
        )

        session = PromptSession(
            history=FileHistory(str(_HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=completer,
            complete_while_typing=False,
            key_bindings=kb,
            bottom_toolbar=_toolbar,
            style=style,
            mouse_support=False,
            enable_history_search=True,
        )
        return session

    except ImportError:
        return None  # Fallback to Rich Prompt


async def run_chat(one_shot_message: Optional[str] = None) -> None:
    """Start an interactive chat session (or run a single message and exit)."""
    from parrrot.core.agent import Agent

    conf = cfg.load()
    name = conf["identity"].get("name", "Parrrot")

    console.print()
    console.print(_header(conf))
    console.print()

    agent = Agent(
        on_tool_call=_on_tool_call,
        on_tool_result=_on_tool_result,
        confirm_callback=_confirm,
    )

    # Verify LLM is reachable
    health = await agent.health_check()
    if not any(health.values()):
        console.print(
            Panel(
                "[bold red]Cannot reach the AI model.[/bold red]\n\n"
                "If using local Ollama, start it with:\n"
                "  [bold cyan]ollama serve[/bold cyan]\n\n"
                "Then make sure your model is pulled:\n"
                f"  [bold cyan]ollama pull {conf['model'].get('local_model', 'llama3.2')}[/bold cyan]",
                title="Connection Error",
                border_style="red",
            )
        )
        return

    if one_shot_message:
        await _handle_message(agent, name, one_shot_message)
        return

    console.print(f"  [dim]Hi! I'm [bold cyan]{name}[/bold cyan]. What can I do for you?[/dim]")
    console.print()

    # Build prompt_toolkit session (graceful fallback to Rich if not installed)
    session = _make_prompt_session(conf)
    verbose = [False]  # mutable flag for /verbose toggle

    while True:
        try:
            if session is not None:
                # prompt_toolkit path — async, with history + completion
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: session.prompt("You: "),
                )
            else:
                # Fallback: plain Rich prompt
                from rich.prompt import Prompt
                user_input = Prompt.ask(
                    Text.from_markup("[bold white]You[/bold white]"),
                    console=console,
                )
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print(f"  [dim]Goodbye![/dim]")
            break

        user_input = (user_input or "").strip()
        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "bye", "goodbye"):
            console.print(f"\n  [dim]{name}: Goodbye! Talk to you soon.[/dim]\n")
            break

        if user_input.startswith("/"):
            result = _handle_slash_command(user_input, conf, name, agent, verbose)
            if result == "exit":
                break
            continue

        await _handle_message(agent, name, user_input, verbose=verbose[0])


async def _handle_message(
    agent, name: str, user_input: str, verbose: bool = False
) -> None:
    _tool_event_buffer.clear()

    response_tokens: list[str] = []

    async def collect_token(token: str) -> None:
        response_tokens.append(token)

    verb = random.choice(_THINKING_VERBS)

    try:
        with console.status(
            f"[dim cyan]{name} is {verb}…[/dim cyan]", spinner="dots"
        ):
            response = await agent.think_and_act(user_input, stream_callback=collect_token)

        full_response = "".join(response_tokens) or response or ""

        if full_response.strip():
            try:
                md = Markdown(full_response)
            except Exception:
                md = full_response  # type: ignore[assignment]

            console.print()
            console.print(
                Panel(
                    md,
                    title=f"[bold green]{name}[/bold green]",
                    border_style="green",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
        else:
            console.print(f"\n  [dim]{name}: (no response)[/dim]")

        # Show tool trace after the answer — only when verbose is on
        if verbose and _tool_event_buffer:
            console.print()
            console.print("  [dim]── tool trace ──[/dim]")
            for event_type, tool_name, data in _tool_event_buffer:
                if event_type == "call":
                    args_preview = ", ".join(
                        f"{k}={repr(v)[:30]}" for k, v in (data or {}).items()  # type: ignore[union-attr]
                    )
                    console.print(f"  [dim cyan]↳ {tool_name}({args_preview})[/dim cyan]")
                else:
                    preview = str(data)[:100].replace("\n", " ")
                    console.print(f"  [dim green]  ✓ {preview}{'…' if len(str(data)) > 100 else ''}[/dim green]")

    except Exception as e:
        console.print()
        _show_error(name, str(e))

    console.print()


async def _on_tool_call(tool_name: str, args: dict) -> None:
    _tool_event_buffer.append(("call", tool_name, args))


async def _on_tool_result(tool_name: str, result: str) -> None:
    _tool_event_buffer.append(("result", tool_name, result))


async def _confirm(prompt: str) -> bool:
    from rich.prompt import Confirm
    console.print()
    return Confirm.ask(f"  [bold yellow]⚠[/bold yellow]  {prompt}", default=False)


def _show_error(name: str, error: str) -> None:
    if "ollama" in error.lower() or "connection" in error.lower():
        msg = (
            f"I couldn't reach my brain (Ollama).\n\n"
            f"Fix: make sure Ollama is running:\n"
            f"  [bold]ollama serve[/bold]"
        )
    elif "model" in error.lower() and "not found" in error.lower():
        msg = (
            f"The model isn't downloaded yet.\n\n"
            f"Fix: [bold]ollama pull <model-name>[/bold]"
        )
    elif "api key" in error.lower() or "401" in error:
        msg = "API key error. Check your key in [bold]~/.parrrot/secrets.json[/bold]"
    else:
        msg = f"Something went wrong: {error}"

    console.print(
        Panel(msg, title=f"[bold red]{name} hit an error[/bold red]", border_style="red")
    )


def _handle_slash_command(
    cmd: str, conf: dict, name: str, agent, verbose: list
) -> Optional[str]:
    """Handle built-in slash commands. Returns 'exit' to break the chat loop."""
    parts = cmd.lstrip("/").split(None, 1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("exit", "quit"):
        console.print(f"\n  [dim]{name}: Goodbye! Talk to you soon.[/dim]\n")
        return "exit"

    elif command == "clear":
        console.clear()
        console.print(_header(cfg.load()))

    elif command in ("new", "reset"):
        agent.clear_history()
        console.print(f"  [dim green]✓ Conversation cleared. Starting fresh.[/dim green]")
        console.print()

    elif command == "status":
        _show_status(conf, name)

    elif command == "memory":
        _show_memory(arg)

    elif command == "tools":
        from parrrot.tools.registry import registry
        console.print()
        for tool in registry.all_tools():
            console.print(f"  [cyan]{tool.name}[/cyan]: [dim]{tool.description}[/dim]")
        console.print()

    elif command == "model":
        mode = conf["model"]["mode"]
        current = conf["model"].get(
            "local_model" if mode == "local" else "cloud_model", "?"
        )
        console.print(f"\n  Active model: [green]{current}[/green] ({mode})\n")

    elif command in ("verbose", "v"):
        verbose[0] = not verbose[0]
        state = "[green]ON[/green]" if verbose[0] else "[dim]OFF[/dim]"
        console.print(f"  Verbose mode: {state}\n")

    elif command == "compact":
        # Summarise and compress conversation to save context
        count = len(agent._conversation)
        if count == 0:
            console.print("  [dim]No conversation to compact.[/dim]\n")
        else:
            agent._maybe_save_summary()
            console.print(
                f"  [dim green]✓ Compacted {count} messages → memory.[/dim green]\n"
            )

    elif command == "history":
        _show_history()

    elif command == "hotkey":
        _show_hotkey_info()

    elif command == "help":
        _show_help()

    else:
        console.print(f"  [dim]Unknown command: /{command}. Type /help for commands.[/dim]")

    return None


def _show_status(conf: dict, name: str) -> None:
    mem_counts = memory.count()
    mode = conf["model"]["mode"]
    model = conf["model"].get("local_model" if mode == "local" else "cloud_model", "?")
    console.print()
    console.print(
        Panel(
            f"  Name: [cyan]{name}[/cyan]\n"
            f"  Model: [green]{model}[/green] ({mode})\n"
            f"  Memory: [yellow]{sum(mem_counts.values())}[/yellow] entries "
            f"([dim]{mem_counts.get('facts',0)} facts, "
            f"{mem_counts.get('events',0)} events, "
            f"{mem_counts.get('tasks',0)} tasks[/dim])\n"
            f"  History file: [dim]{_HISTORY_FILE}[/dim]",
            title="[bold cyan]Status[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()


def _show_history() -> None:
    """Print recent command history from the history file."""
    if not _HISTORY_FILE.exists():
        console.print("  [dim]No history yet.[/dim]\n")
        return
    lines = _HISTORY_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    # prompt_toolkit history format: lines starting with + are entries
    entries = [l[1:] for l in lines if l.startswith("+")][-20:]
    if not entries:
        console.print("  [dim]No history yet.[/dim]\n")
        return
    console.print()
    for i, entry in enumerate(entries, 1):
        console.print(f"  [dim]{i:2}.[/dim] {entry}")
    console.print()


def _show_hotkey_info() -> None:
    console.print()
    console.print(
        Panel(
            "  Global hotkey: [bold cyan]Win + Shift + P[/bold cyan]\n\n"
            "  Start the daemon to enable the global hotkey:\n"
            "    [bold]parrrot daemon[/bold]\n\n"
            "  From anywhere on your PC, press [bold cyan]Win+Shift+P[/bold cyan]\n"
            "  to open or focus the Parrrot chat window.\n\n"
            "  The hotkey requires: [bold]pip install keyboard[/bold]",
            title="[bold cyan]Global Hotkey[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()


def _show_help() -> None:
    console.print()
    console.print("  [bold]Navigation shortcuts (prompt_toolkit):[/bold]")
    console.print("  [cyan]↑ / ↓[/cyan]           Scroll through command history")
    console.print("  [cyan]Ctrl+R[/cyan]           Search history (type to filter)")
    console.print("  [cyan]Tab[/cyan]              Autocomplete commands")
    console.print("  [cyan]Ctrl+L[/cyan]           Clear the screen")
    console.print("  [cyan]Ctrl+C[/cyan]           Cancel current input")
    console.print("  [cyan]Alt+F / Alt+B[/cyan]    Jump word forward/backward")
    console.print()
    console.print("  [bold]Chat commands:[/bold]")
    console.print("  [cyan]/new[/cyan]   [dim]or[/dim] [cyan]/reset[/cyan]    Clear conversation, start fresh")
    console.print("  [cyan]/status[/cyan]             Show model, memory, and config info")
    console.print("  [cyan]/model[/cyan]              Show active model")
    console.print("  [cyan]/verbose[/cyan]            Toggle verbose tool output")
    console.print("  [cyan]/compact[/cyan]            Compress conversation to memory")
    console.print("  [cyan]/memory [query][/cyan]     Search or browse memories")
    console.print("  [cyan]/tools[/cyan]              List all available tools")
    console.print("  [cyan]/history[/cyan]            Show recent command history")
    console.print("  [cyan]/hotkey[/cyan]             Show global hotkey info")
    console.print("  [cyan]/clear[/cyan]              Clear the screen")
    console.print("  [cyan]/help[/cyan]               Show this help")
    console.print()


def _show_memory(query: str) -> None:
    results = memory.recall(query) if query else []
    if not results:
        facts = memory.all_facts()
        if not facts:
            console.print("  [dim]No memories yet.[/dim]")
            return
        console.print()
        for k, v in list(facts.items())[:20]:
            console.print(f"  [cyan]{k}[/cyan]: {v}")
        console.print()
    else:
        console.print()
        for r in results:
            console.print(f"  [cyan]{r['key']}[/cyan] [{r['category']}]: {r['value']}")
        console.print()
