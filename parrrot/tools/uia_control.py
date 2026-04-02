"""
Parrrot — Windows UI Automation (UIA) based PC navigation.

This is the same approach OpenClaw uses: instead of taking a screenshot and
guessing pixel coordinates, we READ the accessibility tree of any app directly.
Every button, input field, menu item, link, checkbox reports its name, role,
and position through Windows UIA — no screenshot, no OCR, no vision model needed.

Works with: Chrome, Firefox, Edge, Notepad, File Explorer, VS Code, Outlook,
Word, Excel, Settings, and virtually any native Windows app.

Requires: pip install pywinauto comtypes
Part of the Parrrot open-source personal AI assistant.
"""

from __future__ import annotations

import time
from typing import Optional

from parrrot.tools.registry import registry

_INSTALL_MSG = (
    "Windows UI Automation requires pywinauto.\n"
    "Install: pip install pywinauto comtypes\n"
    "Then restart Parrrot."
)

# ---------------------------------------------------------------------------
# Element reference store — maps "e1", "e2", ... → UIA element wrapper
# The agent sees  e1: Button 'OK'   e2: Edit 'Search'   e3: MenuItem 'File'
# and can say  window_click("e2")  or  window_type("e2", "hello")
# without ever dealing with pixel coordinates.
# ---------------------------------------------------------------------------
_ref_map: dict[str, object] = {}        # ref → pywinauto element wrapper
_ref_info: dict[str, dict] = {}         # ref → {name, type, value}


def _clear_refs() -> None:
    _ref_map.clear()
    _ref_info.clear()


def _make_ref(counter: list[int]) -> str:
    counter[0] += 1
    return f"e{counter[0]}"


# ---------------------------------------------------------------------------
# Core: snapshot the active window's accessibility tree
# ---------------------------------------------------------------------------

def _window_snapshot(app_title: str = "", max_elements: int = 80) -> str:
    """
    Read the UI element tree of the active window (or a specific app by title).
    Returns a numbered list of every interactive element:
        e1: Button 'OK'
        e2: Edit 'Search bar'  value='hello'
        e3: MenuItem 'File'
        e4: CheckBox 'Enable notifications'  checked=True
        ...

    The agent can then use these refs to click, type, or interact without
    needing pixel coordinates or screenshots.
    """
    try:
        import pywinauto
        from pywinauto import Desktop
        from pywinauto.controls.uia_controls import (
            ButtonWrapper, EditWrapper, ComboBoxWrapper,
        )
    except ImportError:
        return _INSTALL_MSG

    _clear_refs()
    counter = [0]
    lines: list[str] = []

    # Control types we care about — everything interactive
    _INTERACTIVE = {
        "Button", "Edit", "ComboBox", "CheckBox", "RadioButton",
        "MenuItem", "ListItem", "Hyperlink", "Tab", "TabItem",
        "ToolBar", "ToolBarButton", "Slider", "Spinner",
        "TreeItem", "DataItem", "SplitButton", "ToggleButton",
        "Menu", "MenuBar", "ScrollBar",
    }
    # Also include Text if it has meaningful content (links, labels)
    _TEXT_MIN_LEN = 2

    try:
        desktop = Desktop(backend="uia")

        if app_title:
            wins = desktop.windows(title_re=f".*{app_title}.*", visible_only=True)
            if not wins:
                return f"No window found matching '{app_title}'. Use window_list_apps() to see open apps."
            target = wins[0]
        else:
            target = desktop.get_active()

        if target is None:
            return "No active window found. Click on an app first."

        win_title = "unknown"
        try:
            win_title = target.window_text() or "unknown"
        except Exception:
            pass

        lines.append(f"Window: '{win_title}'")
        lines.append("")

        def _collect(element, depth: int = 0) -> None:
            if counter[0] >= max_elements:
                return
            try:
                ctrl_type = element.element_info.control_type or ""
                name = (element.element_info.name or "").strip()
                rect = element.element_info.rectangle

                # Skip invisible or zero-size elements
                if rect and (rect.width() <= 0 or rect.height() <= 0):
                    pass  # still collect — some controls report 0 but are real
                if not ctrl_type:
                    return

                extra_parts: list[str] = []

                # Collect value for editable fields
                if ctrl_type in ("Edit", "ComboBox"):
                    try:
                        val = element.get_value() if hasattr(element, "get_value") else ""
                        if val:
                            extra_parts.append(f"value='{val[:60]}'")
                    except Exception:
                        pass

                # Collect checked state
                if ctrl_type in ("CheckBox", "RadioButton", "ToggleButton"):
                    try:
                        state = element.get_toggle_state() if hasattr(element, "get_toggle_state") else None
                        if state is not None:
                            extra_parts.append(f"checked={bool(state)}")
                    except Exception:
                        pass

                # Only include elements we care about
                include = ctrl_type in _INTERACTIVE
                if ctrl_type == "Text" and name and len(name) >= _TEXT_MIN_LEN:
                    include = True  # keep meaningful text labels

                if include and name:
                    ref = _make_ref(counter)
                    extra = ("  " + "  ".join(extra_parts)) if extra_parts else ""
                    lines.append(f"  {ref}: {ctrl_type} '{name}'{extra}")
                    _ref_map[ref] = element
                    _ref_info[ref] = {
                        "name": name,
                        "type": ctrl_type,
                        "extra": extra_parts,
                    }

            except Exception:
                pass

            # Recurse into children
            try:
                for child in element.children():
                    if counter[0] >= max_elements:
                        break
                    _collect(child, depth + 1)
            except Exception:
                pass

        _collect(target)

        if not _ref_map:
            return (
                f"Window '{win_title}' has no readable UI elements.\n"
                "This can happen if the app uses a non-standard rendering engine.\n"
                "Try: read_screen_text() for OCR, or ask_screen() for vision-based reading."
            )

        if counter[0] >= max_elements:
            lines.append(f"\n  ... (showing first {max_elements} elements, use max_elements= to see more)")

        lines.append(f"\n  Total: {len(_ref_map)} elements")
        lines.append("  Use window_click('e1') or window_type('e2', 'text') to interact.")

        return "\n".join(lines)

    except Exception as e:
        return f"UI snapshot failed: {e}\nTip: Run Parrrot as Administrator if you get permission errors."


# ---------------------------------------------------------------------------
# Click an element by ref (e1, e2, ...) or by name/text
# ---------------------------------------------------------------------------

def _window_click(ref_or_name: str, double: bool = False) -> str:
    """
    Click a UI element in the active window.
    ref_or_name: either a ref from window_snapshot() like 'e3',
                 or a plain name like 'OK' or 'Submit'.
    """
    try:
        import pywinauto
    except ImportError:
        return _INSTALL_MSG

    # Try ref lookup first
    element = _ref_map.get(ref_or_name)
    info = _ref_info.get(ref_or_name, {})

    # If not a ref, search by name in existing snapshot
    if element is None:
        query = ref_or_name.lower()
        for ref, inf in _ref_info.items():
            if query in inf.get("name", "").lower():
                element = _ref_map[ref]
                info = inf
                break

    if element is None:
        return (
            f"Element '{ref_or_name}' not found.\n"
            "Run window_snapshot() first to see all elements, then use their ref (e1, e2, ...)."
        )

    try:
        if double:
            element.double_click_input()
        else:
            element.click_input()
        name = info.get("name", ref_or_name)
        return f"Clicked: {info.get('type', '')} '{name}'"
    except Exception as e:
        # Fallback: invoke (works for menu items and some buttons)
        try:
            element.invoke()
            return f"Invoked: '{info.get('name', ref_or_name)}'"
        except Exception:
            return f"Click failed on '{ref_or_name}': {e}"


# ---------------------------------------------------------------------------
# Type text into an element by ref or name
# ---------------------------------------------------------------------------

def _window_type(ref_or_name: str, text: str, clear_first: bool = True) -> str:
    """
    Type text into a field in the active window.
    ref_or_name: ref from window_snapshot() like 'e2', or field name/label.
    """
    try:
        import pywinauto
    except ImportError:
        return _INSTALL_MSG

    element = _ref_map.get(ref_or_name)
    info = _ref_info.get(ref_or_name, {})

    if element is None:
        query = ref_or_name.lower()
        for ref, inf in _ref_info.items():
            if query in inf.get("name", "").lower() and inf.get("type") in (
                "Edit", "ComboBox", "RichEdit", "Document"
            ):
                element = _ref_map[ref]
                info = inf
                break

    if element is None:
        return (
            f"Field '{ref_or_name}' not found.\n"
            "Run window_snapshot() to see all editable fields (Edit, ComboBox)."
        )

    try:
        element.click_input()
        time.sleep(0.1)
        if clear_first:
            element.type_keys("^a{DELETE}", with_spaces=True)
            time.sleep(0.05)
        element.type_keys(text, with_spaces=True)
        return f"Typed into '{info.get('name', ref_or_name)}': {text[:60]}{'...' if len(text) > 60 else ''}"
    except Exception:
        # Fallback: set_edit_text for simple Edit controls
        try:
            element.set_edit_text(text)
            return f"Set text in '{info.get('name', ref_or_name)}': {text[:60]}"
        except Exception as e2:
            return f"Type failed on '{ref_or_name}': {e2}"


# ---------------------------------------------------------------------------
# Select a dropdown/combobox option by ref
# ---------------------------------------------------------------------------

def _window_select(ref_or_name: str, option: str) -> str:
    """Select an option from a dropdown/combobox."""
    try:
        import pywinauto
    except ImportError:
        return _INSTALL_MSG

    element = _ref_map.get(ref_or_name)
    info = _ref_info.get(ref_or_name, {})

    if element is None:
        query = ref_or_name.lower()
        for ref, inf in _ref_info.items():
            if query in inf.get("name", "").lower() and inf.get("type") == "ComboBox":
                element = _ref_map[ref]
                info = inf
                break

    if element is None:
        return f"Dropdown '{ref_or_name}' not found. Run window_snapshot() first."

    try:
        element.select(option)
        return f"Selected '{option}' in '{info.get('name', ref_or_name)}'"
    except Exception as e:
        return f"Select failed: {e}"


# ---------------------------------------------------------------------------
# List all open apps / windows
# ---------------------------------------------------------------------------

def _window_list_apps() -> str:
    """
    List all open application windows on the desktop.
    Shows title + process name so you can target a specific window.
    """
    try:
        import pywinauto
        from pywinauto import Desktop
    except ImportError:
        return _INSTALL_MSG

    try:
        desktop = Desktop(backend="uia")
        wins = desktop.windows(visible_only=True)
        lines: list[str] = []
        for w in wins:
            try:
                title = w.window_text()
                proc = ""
                try:
                    import psutil
                    p = psutil.Process(w.process_id())
                    proc = p.name()
                except Exception:
                    pass
                if title and title.strip():
                    lines.append(f"  '{title}'  [{proc}]")
            except Exception:
                pass
        if not lines:
            return "No open windows found."
        return "Open windows:\n" + "\n".join(lines[:40])
    except Exception as e:
        return f"Could not list apps: {e}"


# ---------------------------------------------------------------------------
# Find elements by query in the current snapshot
# ---------------------------------------------------------------------------

def _window_find(query: str) -> str:
    """
    Search the current window snapshot for elements matching a description.
    Returns matching refs and their details.
    Run window_snapshot() first to populate the element list.
    """
    if not _ref_info:
        return "No snapshot loaded. Run window_snapshot() first."

    query_lower = query.lower()
    matches: list[str] = []

    for ref, info in _ref_info.items():
        name = info.get("name", "").lower()
        ctrl_type = info.get("type", "").lower()
        if query_lower in name or query_lower in ctrl_type:
            extra = "  " + "  ".join(info.get("extra", []))
            matches.append(f"  {ref}: {info['type']} '{info['name']}'{extra}")

    if not matches:
        return f"No elements matching '{query}'. Run window_snapshot() to refresh."
    return f"Elements matching '{query}':\n" + "\n".join(matches)


# ---------------------------------------------------------------------------
# Focus / switch to an app window by title
# ---------------------------------------------------------------------------

def _window_focus(title: str) -> str:
    """
    Switch to an application window by title (partial match).
    Example: window_focus("Notepad") or window_focus("Chrome")
    """
    try:
        import pywinauto
        from pywinauto import Desktop
    except ImportError:
        return _INSTALL_MSG

    try:
        desktop = Desktop(backend="uia")
        wins = desktop.windows(title_re=f".*{title}.*", visible_only=True)
        if not wins:
            return f"No window found matching '{title}'. Use window_list_apps() to see all open apps."
        wins[0].set_focus()
        time.sleep(0.3)
        return f"Focused: '{wins[0].window_text()}'"
    except Exception as e:
        return f"Could not focus '{title}': {e}"


# ---------------------------------------------------------------------------
# Get info about a specific element
# ---------------------------------------------------------------------------

def _window_element_info(ref: str) -> str:
    """Get detailed info about a specific element ref from the last snapshot."""
    if ref not in _ref_map:
        return f"Ref '{ref}' not found. Run window_snapshot() first."

    info = _ref_info[ref]
    element = _ref_map[ref]
    lines = [f"  ref:  {ref}",
             f"  type: {info.get('type','')}",
             f"  name: {info.get('name','')}"]

    try:
        rect = element.element_info.rectangle
        lines.append(f"  rect: ({rect.left}, {rect.top}) → ({rect.right}, {rect.bottom})")
        lines.append(f"  size: {rect.width()}×{rect.height()}")
    except Exception:
        pass

    try:
        enabled = element.element_info.enabled
        lines.append(f"  enabled: {enabled}")
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scroll within the active window or a specific element
# ---------------------------------------------------------------------------

def _window_scroll(direction: str = "down", amount: int = 3, ref: str = "") -> str:
    """Scroll the active window or a specific element (by ref)."""
    try:
        import pywinauto
    except ImportError:
        return _INSTALL_MSG

    try:
        import pyautogui
        w, h = pyautogui.size()

        target_x, target_y = w // 2, h // 2

        if ref and ref in _ref_map:
            try:
                rect = _ref_map[ref].element_info.rectangle
                target_x = (rect.left + rect.right) // 2
                target_y = (rect.top + rect.bottom) // 2
            except Exception:
                pass

        # Move mouse to target and scroll
        pyautogui.moveTo(target_x, target_y, duration=0.1)
        scroll_clicks = -amount if direction == "down" else amount
        pyautogui.scroll(scroll_clicks)
        return f"Scrolled {direction} {amount} steps"
    except ImportError:
        return "pyautogui not installed: pip install pyautogui"
    except Exception as e:
        return f"Scroll failed: {e}"


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

registry.register(
    "window_snapshot",
    "Read the UI element tree of the active window — lists every button, input, "
    "menu item, checkbox etc. with a ref (e1, e2, ...). Use refs to click/type "
    "without pixel coordinates. Much faster and more reliable than screenshot+OCR.",
    {
        "app_title": "optional: focus a specific app by title (partial match)",
        "max_elements": "max elements to return (default 80)",
    },
)(_window_snapshot)

registry.register(
    "window_click",
    "Click a UI element in the active window. Use a ref from window_snapshot() "
    "like 'e3', or a plain name like 'OK' or 'Sign in'.",
    {
        "ref_or_name": "ref (e3) or element name to click",
        "double": "true for double-click (default false)",
    },
)(_window_click)

registry.register(
    "window_type",
    "Type text into a field in the active window. Use a ref from window_snapshot() "
    "like 'e2', or the field's label/placeholder name.",
    {
        "ref_or_name": "ref (e2) or field name",
        "text": "text to type",
        "clear_first": "clear existing content first (default true)",
    },
)(_window_type)

registry.register(
    "window_select",
    "Select an option from a dropdown or combobox in the active window.",
    {
        "ref_or_name": "ref or combobox name from window_snapshot()",
        "option": "option text to select",
    },
)(_window_select)

registry.register(
    "window_list_apps",
    "List all open application windows on the desktop with their titles and process names.",
    {},
)(_window_list_apps)

registry.register(
    "window_find",
    "Search the current window snapshot for elements matching a query. "
    "Run window_snapshot() first.",
    {"query": "text to search for in element names or types"},
)(_window_find)

registry.register(
    "window_focus",
    "Switch to / bring to foreground an application window by title (partial match). "
    "Example: 'Chrome', 'Notepad', 'File Explorer', 'Settings'.",
    {"title": "partial window title to match"},
)(_window_focus)

registry.register(
    "window_element_info",
    "Get detailed info (type, name, position, size, enabled state) about a specific "
    "element ref from the last window_snapshot().",
    {"ref": "element ref like 'e3'"},
)(_window_element_info)

registry.register(
    "window_scroll",
    "Scroll the active window or a specific element up or down.",
    {
        "direction": "up or down (default: down)",
        "amount": "scroll steps (default: 3)",
        "ref": "optional element ref to scroll within",
    },
)(_window_scroll)
