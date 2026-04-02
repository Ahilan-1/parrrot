"""
Parrrot — Tool registry and dispatcher
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    parameters: dict[str, str] = field(default_factory=dict)  # param_name -> description
    is_async: bool = False
    requires_confirm: bool = False  # dangerous tools need user confirmation


class ToolRegistry:
    """Central registry for all Parrrot tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, str] | None = None,
        requires_confirm: bool = False,
    ):
        """Decorator to register a function as a tool."""
        def decorator(func: Callable) -> Callable:
            is_async = inspect.iscoroutinefunction(func)
            self._tools[name] = ToolDef(
                name=name,
                description=description,
                func=func,
                parameters=parameters or {},
                is_async=is_async,
                requires_confirm=requires_confirm,
            )
            return func
        return decorator

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def all_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def tool_list_string(self) -> str:
        """Formatted string of all tools for the system prompt."""
        lines: list[str] = []
        for tool in self._tools.values():
            params = ", ".join(
                f"{k}: {v}" for k, v in tool.parameters.items()
            )
            confirm_note = " [REQUIRES CONFIRMATION]" if tool.requires_confirm else ""
            lines.append(f"- {tool.name}({params}){confirm_note}: {tool.description}")
        return "\n".join(lines)

    async def dispatch(
        self,
        name: str,
        args: dict[str, Any],
        confirm_callback: Callable[[str], Awaitable[bool]] | None = None,
    ) -> str:
        """Execute a tool by name with args. Returns result as string."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: Unknown tool '{name}'. Available tools: {', '.join(self._tools)}"

        if tool.requires_confirm and confirm_callback:
            args_str = json.dumps(args, indent=2)
            confirmed = await confirm_callback(
                f"Tool '{name}' needs your confirmation.\nArgs:\n{args_str}\nProceed?"
            )
            if not confirmed:
                return f"Tool '{name}' was cancelled by the user."

        try:
            if tool.is_async:
                result = await tool.func(**args)
            else:
                result = tool.func(**args)
            return str(result) if result is not None else "(done)"
        except TypeError as e:
            return f"Error: Wrong arguments for '{name}': {e}"
        except Exception as e:
            return f"Error running '{name}': {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Parse tool calls from LLM response
# ---------------------------------------------------------------------------

# Pattern 1: <tool>NAME</tool><args>{...}</args>  — args are optional
_TOOL_XML_RE = re.compile(
    r"<tool>\s*([\w_]+)\s*</tool>\s*(?:<args>(.*?)</args>)?",
    re.DOTALL | re.IGNORECASE,
)

# Pattern 2: <tool>NAME()</tool> or <tool>NAME({"key":"val"})</tool>
_TOOL_CALL_RE = re.compile(
    r"<tool>\s*([\w_]+)\s*\((.*?)\)\s*</tool>",
    re.DOTALL | re.IGNORECASE,
)

# Pattern 3: bare JSON tool call the LLM sometimes emits
# {"tool": "NAME", "args": {...}}
_TOOL_JSON_RE = re.compile(
    r'\{"tool"\s*:\s*"([\w_]+)"\s*,\s*"args"\s*:\s*(\{.*?\})\s*\}',
    re.DOTALL,
)


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """
    Extract tool calls from LLM output.
    Handles all formats the LLM might use:
      <tool>open_gmail</tool>                         (no args)
      <tool>open_gmail</tool><args>{}</args>          (explicit empty args)
      <tool>web_search</tool><args>{"query":"x"}</args>
      <tool>open_gmail()</tool>                       (python-call style)
      <tool>web_search({"query":"x"})</tool>
      {"tool": "open_gmail", "args": {}}              (JSON style)
    """
    seen: set[str] = set()  # deduplicate by (name, args_str)
    results: list[tuple[str, dict]] = []

    def _add(name: str, args_str: str) -> None:
        name = name.strip()
        args_str = (args_str or "").strip()
        key = f"{name}:{args_str}"
        if key in seen:
            return
        seen.add(key)
        if not args_str or args_str in ("{}", ""):
            args: dict = {}
        else:
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                # Try wrapping as string value
                args = {"raw": args_str}
        results.append((name, args))

    # Pattern 1: <tool>NAME</tool> with optional <args>
    for m in _TOOL_XML_RE.finditer(text):
        _add(m.group(1), m.group(2) or "")

    # Pattern 2: <tool>NAME(...)</tool>
    for m in _TOOL_CALL_RE.finditer(text):
        _add(m.group(1), m.group(2))

    # Pattern 3: JSON object style
    for m in _TOOL_JSON_RE.finditer(text):
        _add(m.group(1), m.group(2))

    return results


def strip_tool_calls(text: str) -> str:
    """Remove all recognised tool call blocks from a string."""
    text = _TOOL_XML_RE.sub("", text)
    text = _TOOL_CALL_RE.sub("", text)
    text = _TOOL_JSON_RE.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Global registry instance
# ---------------------------------------------------------------------------

registry = ToolRegistry()


def load_all_tools() -> None:
    """Import all tool modules so they register themselves."""
    tool_modules = [
        "parrrot.tools.filesystem",
        "parrrot.tools.shell",
        "parrrot.tools.system_info",
        "parrrot.tools.notifications",
        # Screen + PC control + browser + email are core — they degrade
        # gracefully if mss/pyautogui aren't installed.
        "parrrot.tools.screen",
        "parrrot.tools.pc_control",
        "parrrot.tools.browser_control",
        "parrrot.tools.email_tool",
        "parrrot.tools.learning_tools",
        "parrrot.tools.chatgpt_tool",
    ]
    # Optional modules that may not have their deps installed
    optional_modules = [
        "parrrot.tools.uia_control",   # Windows UI Automation — desktop app navigation
        "parrrot.tools.browser_cdp",   # CDP browser control — fast web navigation (all languages)
        "parrrot.tools.browser",       # Playwright (fully optional)
        "parrrot.tools.youtube",
        "parrrot.tools.calendar_tool",
    ]
    for mod in tool_modules:
        importlib.import_module(mod)
    for mod in optional_modules:
        try:
            importlib.import_module(mod)
        except ImportError:
            pass  # dep not installed — tool simply won't be available
