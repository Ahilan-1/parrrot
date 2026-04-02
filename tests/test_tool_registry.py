"""Tests for the tool registry and parser."""

import pytest


def test_register_and_dispatch_sync():
    from parrrot.tools.registry import ToolRegistry

    reg = ToolRegistry()

    @reg.register("echo", "Echo a message", {"msg": "message"})
    def echo(msg: str) -> str:
        return f"Echo: {msg}"

    import asyncio
    result = asyncio.run(reg.dispatch("echo", {"msg": "hello"}))
    assert result == "Echo: hello"


def test_dispatch_unknown_tool():
    from parrrot.tools.registry import ToolRegistry
    import asyncio

    reg = ToolRegistry()
    result = asyncio.run(reg.dispatch("nonexistent", {}))
    assert "Unknown tool" in result


def test_parse_tool_calls():
    from parrrot.tools.registry import parse_tool_calls

    text = 'I will search for you. <tool>web_search</tool><args>{"query": "weather"}</args>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0][0] == "web_search"
    assert calls[0][1] == {"query": "weather"}


def test_parse_multiple_tool_calls():
    from parrrot.tools.registry import parse_tool_calls

    text = (
        '<tool>list_files</tool><args>{"path": "."}</args> '
        '<tool>get_system_info</tool><args>{}</args>'
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0][0] == "list_files"
    assert calls[1][0] == "get_system_info"


def test_parse_no_tool_calls():
    from parrrot.tools.registry import parse_tool_calls

    calls = parse_tool_calls("Just a normal response with no tools.")
    assert calls == []


def test_strip_tool_calls():
    from parrrot.tools.registry import strip_tool_calls

    text = 'Searching... <tool>web_search</tool><args>{"query": "test"}</args> Done.'
    result = strip_tool_calls(text)
    assert "<tool>" not in result
    assert "Searching..." in result
    assert "Done." in result
