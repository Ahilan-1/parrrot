"""
Parrrot — CDP (Chrome DevTools Protocol) browser control.

Connects to YOUR existing Chrome/Edge/Brave (with all your logins & sessions).
Reads the page DOM directly — instant, works with ALL languages including
Indian scripts (Hindi, Tamil, Telugu, Malayalam, Bengali, Kannada, etc.).
No screenshots. No OCR. No pixel guessing. No waiting.

This is the same core approach OpenClaw uses for browser automation.

HOW TO SET UP (one time):
  Option A — Use the tool:  browser_launch_debug()
  Option B — Manual:
    Chrome: right-click shortcut → Properties → add  --remote-debugging-port=9222
    Edge:   same with msedge.exe
    Then close and reopen Chrome from that shortcut.

After that, page_* tools work instantly with your real browser sessions.

Requires: pip install websocket-client requests
"""

from __future__ import annotations

import json
import subprocess
import platform
import os
import shutil
import time
import threading
from typing import Any, Optional

from parrrot.tools.registry import registry

_CDP_PORT = 9222
_CDP_HOST = "127.0.0.1"

# Active WebSocket connection to the current tab
_ws_lock = threading.Lock()
_ws = None          # websocket.WebSocket instance
_msg_id = [0]
_recv_timeout = 8   # seconds to wait for CDP response

# Element ref store: e1, e2, ... → {selector, text, tag, type}
_ref_map: dict[str, dict] = {}

_INSTALL_MSG = (
    "CDP browser control requires websocket-client.\n"
    "Install: pip install websocket-client requests\n"
    "Then run: browser_launch_debug() to open Chrome with debug mode."
)


# ---------------------------------------------------------------------------
# Low-level CDP helpers
# ---------------------------------------------------------------------------

def _connect_ws(tab_ws_url: str) -> bool:
    """Open WebSocket connection to a CDP tab. Returns True on success."""
    global _ws
    try:
        import websocket
        with _ws_lock:
            if _ws:
                try:
                    _ws.close()
                except Exception:
                    pass
            _ws = websocket.WebSocket()
            _ws.connect(tab_ws_url, timeout=5)
        return True
    except Exception:
        return False


def _ensure_connected() -> bool:
    """
    Ensure we have an active CDP websocket.
    If not connected yet, attempt to connect to the most recent page tab (index 0).
    """
    global _ws
    if _ws is not None:
        return True
    tabs = _get_tabs()
    if not tabs:
        return False
    idx = 0
    tab = tabs[idx]
    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return False
    return _connect_ws(ws_url)


def _cdp(method: str, params: dict | None = None) -> dict:
    """Send one CDP command and return the result dict."""
    import websocket
    with _ws_lock:
        if _ws is None and not _ensure_connected():
            raise RuntimeError("Not connected. Run page_connect() first.")
        _msg_id[0] += 1
        msg = json.dumps({"id": _msg_id[0], "method": method, "params": params or {}})
        _ws.send(msg)
        _ws.settimeout(_recv_timeout)
        while True:
            raw = _ws.recv()
            data = json.loads(raw)
            if data.get("id") == _msg_id[0]:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})


def _js(expression: str, timeout_ms: int = 5000) -> Any:
    """Evaluate JavaScript and return the value."""
    result = _cdp("Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
        "timeout": timeout_ms,
    })
    if result.get("exceptionDetails"):
        exc = result["exceptionDetails"]
        raise RuntimeError(f"JS error: {exc.get('text', exc)}")
    val = result.get("result", {})
    return val.get("value")


def _wait_for_load(max_wait: float = 6.0, poll: float = 0.25) -> None:
    """Wait until document.readyState == 'complete' or timeout."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            state = _js("document.readyState")
            if state == "complete":
                return
        except Exception:
            pass
        time.sleep(poll)


# ---------------------------------------------------------------------------
# Get list of open Chrome tabs via HTTP
# ---------------------------------------------------------------------------

def _get_tabs() -> list[dict]:
    """Return list of open tabs from Chrome debug endpoint."""
    try:
        import requests as _req
        r = _req.get(f"http://{_CDP_HOST}:{_CDP_PORT}/json", timeout=3)
        return [t for t in r.json() if t.get("type") == "page"]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal: find browser exe
# ---------------------------------------------------------------------------

def _find_browser_exe(browser: str = "auto") -> tuple[str, str]:
    """Returns (exe_path, browser_name) or ('', '') if not found."""
    sys = platform.system()
    candidates: list[tuple[str, str]] = []

    if browser in ("chrome", "auto"):
        if sys == "Windows":
            for path in [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
            ]:
                candidates.append((path, "Chrome"))
        elif sys == "Darwin":
            candidates.append(("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "Chrome"))
        else:
            for w in [shutil.which("google-chrome"), shutil.which("chromium-browser")]:
                if w:
                    candidates.append((w, "Chrome"))

    if browser in ("edge", "auto"):
        if sys == "Windows":
            for path in [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]:
                candidates.append((path, "Edge"))
        elif sys == "Darwin":
            candidates.append(("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Edge"))

    if browser in ("brave", "auto"):
        if sys == "Windows":
            for path in [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            ]:
                candidates.append((path, "Brave"))

    for exe, name in candidates:
        if exe and os.path.isfile(exe):
            return exe, name
    return "", ""


def _kill_browser_processes(browser_name: str) -> int:
    """Kill existing browser processes so we can relaunch with debug port. Returns count killed."""
    killed = 0
    try:
        import psutil
        exe_map = {
            "Chrome": "chrome.exe",
            "Edge": "msedge.exe",
            "Brave": "brave.exe",
            "auto": None,
        }
        target = exe_map.get(browser_name)
        for proc in psutil.process_iter(["name", "pid"]):
            pname = (proc.info.get("name") or "").lower()
            if target:
                if pname == target.lower():
                    proc.terminate()
                    killed += 1
            else:
                if pname in ("chrome.exe", "msedge.exe", "brave.exe"):
                    proc.terminate()
                    killed += 1
    except Exception:
        pass
    return killed


def _poll_debug_port(timeout: float = 10.0) -> list[dict]:
    """Poll http://localhost:9222/json until tabs appear or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        tabs = _get_tabs()
        if tabs:
            return tabs
        time.sleep(0.5)
    return []


# ---------------------------------------------------------------------------
# Tool: Launch Chrome/Edge with debug port
# ---------------------------------------------------------------------------

def _browser_launch_debug(browser: str = "auto", close_existing: bool = True) -> str:
    """
    Launch Chrome/Edge/Brave with the remote debugging port (9222) enabled.
    Your logins and profile are preserved — same user data directory is used.

    IMPORTANT: If the browser is already open without debug mode, it must be
    closed first (close_existing=True does this automatically).

    browser: 'chrome', 'edge', 'brave', or 'auto' (tries all).
    close_existing: close running browser first so debug port can be set (default true).
    """
    # Check if debug port already works (browser already running with it)
    existing_tabs = _get_tabs()
    if existing_tabs:
        return (
            f"Browser already running with debug port {_CDP_PORT}! "
            f"{len(existing_tabs)} tab(s) found.\n"
            f"Run: page_connect()  to link to the active tab."
        )

    exe, name = _find_browser_exe(browser)
    if not exe:
        return (
            f"Could not find {browser} browser.\n\n"
            "Manual one-time setup:\n"
            f"  1. Close your browser completely\n"
            f"  2. Right-click browser shortcut → Properties\n"
            f"  3. In Target field, add at the end:  --remote-debugging-port=9222\n"
            f"  4. Click OK, then open browser from that shortcut\n"
            f"  5. Run page_connect()"
        )

    # Close existing browser so we can relaunch with debug port
    killed = 0
    if close_existing:
        killed = _kill_browser_processes(name)
        if killed:
            time.sleep(1.5)  # wait for processes to fully exit

    # Launch with debug port — same profile as normal usage (logins preserved)
    args = [
        exe,
        f"--remote-debugging-port={_CDP_PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        subprocess.Popen(args)
    except Exception as e:
        return f"Failed to launch {name}: {e}"

    # Poll until debug port is ready (up to 12 seconds)
    tabs = _poll_debug_port(timeout=12.0)

    if tabs:
        closed_msg = f" (closed {killed} existing process(es) first)" if killed else ""
        return (
            f"Launched {name} with debug port {_CDP_PORT}{closed_msg}.\n"
            f"{len(tabs)} tab(s) ready. Your logins and profile are preserved.\n\n"
            f"Now run: page_connect()"
        )

    return (
        f"Launched {name} but debug port {_CDP_PORT} is not responding.\n\n"
        "This usually means another browser instance is blocking the port.\n\n"
        "Fix — open Task Manager, end ALL Edge/Chrome processes, then run:\n"
        f"  browser_launch_debug(browser='{browser.lower()}', close_existing=True)"
    )


# ---------------------------------------------------------------------------
# Tool: Connect to running browser
# ---------------------------------------------------------------------------

def _page_connect(tab_index: int = 0) -> str:
    """
    Connect to your running Chrome/Edge/Brave browser.
    The browser must be open (use browser_launch_debug() if not).

    tab_index: which tab to connect to (0 = most recent/active, default).
    """
    try:
        import websocket
    except ImportError:
        return _INSTALL_MSG

    tabs = _get_tabs()
    if not tabs:
        return (
            f"No browser found on debug port {_CDP_PORT}.\n\n"
            "The browser must be CLOSED and reopened with the debug port flag.\n\n"
            "Run this to do it automatically:\n"
            "  browser_launch_debug(browser='edge')    ← for Edge\n"
            "  browser_launch_debug(browser='chrome')  ← for Chrome\n\n"
            "This will close your browser, relaunch it with debug mode,\n"
            "and your logins/profile will be preserved."
        )

    idx = min(tab_index, len(tabs) - 1)
    tab = tabs[idx]
    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return f"Tab {idx} has no WebSocket URL. Try tab_index=0."

    ok = _connect_ws(ws_url)
    if not ok:
        return "WebSocket connection failed. Is Chrome fully loaded?"

    title = tab.get("title", "untitled")
    url = tab.get("url", "")
    tabs_summary = "\n".join(
        f"  [{i}] {t.get('title','')[:60]}  ({t.get('url','')[:50]})"
        for i, t in enumerate(tabs)
    )
    return (
        f"Connected to tab [{idx}]: '{title}'\n"
        f"URL: {url}\n\n"
        f"All open tabs:\n{tabs_summary}\n\n"
        f"Use page_connect(tab_index=N) to switch tabs."
    )


# ---------------------------------------------------------------------------
# Tool: Navigate to URL
# ---------------------------------------------------------------------------

def _page_navigate(url: str, wait_load: bool = True) -> str:
    """
    Navigate the connected browser tab to a URL.
    Waits for the page to finish loading before returning.
    """
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url
    try:
        _cdp("Page.navigate", {"url": url})
        if wait_load:
            _wait_for_load(max_wait=10.0)
        title = _js("document.title") or ""
        return f"Navigated to: {title or url}\nURL: {url}"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Navigation failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Read page text — handles ALL languages including Indian scripts
# ---------------------------------------------------------------------------

def _page_read(max_chars: int = 6000) -> str:
    """
    Read all text on the current page directly from the DOM.
    Works with ALL languages: Hindi, Tamil, Telugu, Malayalam, Bengali, etc.
    Instant — no screenshot, no OCR.
    """
    try:
        # Get clean text — removes scripts/styles, preserves structure
        script = r"""
(function() {
    // Remove script, style, noscript tags for clean text
    var clone = document.body.cloneNode(true);
    ['script','style','noscript','svg'].forEach(function(tag) {
        clone.querySelectorAll(tag).forEach(function(el) { el.remove(); });
    });
    // Get text, collapse whitespace
    var text = clone.innerText || clone.textContent || '';
    return text.replace(/\n{3,}/g, '\n\n').trim();
})()
"""
        text = _js(script) or ""
        title = _js("document.title") or ""
        url = _js("location.href") or ""

        if not text:
            return "Page has no readable text content."

        result = f"Page: {title}\nURL: {url}\n\n{text}"
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n... (truncated, {len(result)} total chars)"
        return result
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Page read failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Snapshot — get all interactive elements with refs
# ---------------------------------------------------------------------------

def _page_snapshot(include_text: bool = False) -> str:
    """
    Get all interactive elements on the page with stable refs (e1, e2, ...).
    Returns buttons, inputs, links, selects, checkboxes — everything clickable.
    Works with Indian language page content (reads text from DOM, not OCR).

    Use the refs with page_click('e3') or page_type('e2', 'text').
    """
    _ref_map.clear()

    script = r"""
(function() {
    var results = [];
    var seen = new Set();

    // Selectors for all interactive elements
    var selectors = [
        'a[href]', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="tab"]',
        '[role="menuitem"]', '[role="option"]', '[role="checkbox"]',
        '[role="radio"]', '[role="combobox"]', '[role="textbox"]',
        '[role="searchbox"]', '[onclick]', 'label[for]',
        'summary',  // <details> toggles
    ];

    var elements = document.querySelectorAll(selectors.join(','));

    elements.forEach(function(el) {
        if (seen.has(el)) return;
        seen.add(el);

        // Skip hidden elements
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return;
        var rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        var tag = el.tagName.toLowerCase();
        var type = el.type || '';
        var role = el.getAttribute('role') || tag;

        // Get the best label for this element
        var label = (
            el.innerText ||
            el.textContent ||
            el.value ||
            el.placeholder ||
            el.getAttribute('aria-label') ||
            el.getAttribute('title') ||
            el.getAttribute('alt') ||
            el.name ||
            ''
        ).trim().replace(/\s+/g, ' ').slice(0, 80);

        // Current value for inputs
        var value = '';
        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            value = (el.value || '').slice(0, 60);
        }

        // Checked state
        var checked = null;
        if (type === 'checkbox' || type === 'radio') {
            checked = el.checked;
        }

        // Disabled?
        var disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';

        if (label || value) {
            results.push({
                tag: tag,
                type: type,
                role: role,
                label: label,
                value: value,
                checked: checked,
                disabled: disabled,
                x: Math.round(rect.left + rect.width/2),
                y: Math.round(rect.top + rect.height/2),
            });
        }
    });

    return JSON.stringify(results);
})()
"""
    try:
        raw = _js(script) or "[]"
        elements = json.loads(raw)
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Snapshot failed: {e}"

    if not elements:
        return "No interactive elements found on this page."

    lines: list[str] = []
    title = ""
    url = ""
    try:
        title = _js("document.title") or ""
        url = _js("location.href") or ""
        lines.append(f"Page: {title}")
        lines.append(f"URL: {url}")
        lines.append("")
    except Exception:
        pass

    for i, el in enumerate(elements[:100]):
        ref = f"e{i+1}"
        _ref_map[ref] = el

        tag = el["tag"]
        role = el.get("role") or tag
        label = el.get("label", "")
        value = el.get("value", "")
        checked = el.get("checked")
        disabled = el.get("disabled", False)

        parts = [f"  {ref}: {role}"]
        if label:
            parts.append(f"'{label}'")
        if value:
            parts.append(f"value='{value}'")
        if checked is not None:
            parts.append(f"checked={checked}")
        if disabled:
            parts.append("[disabled]")

        lines.append(" ".join(parts))

    if len(elements) > 100:
        lines.append(f"\n  ... (showing 100 of {len(elements)} elements)")

    lines.append(f"\n  Use page_click('e1') or page_type('e2', 'text')")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Click an element by ref or text
# ---------------------------------------------------------------------------

def _page_click(ref_or_text: str) -> str:
    """
    Click an element on the page.
    ref_or_text: a ref from page_snapshot() like 'e3',
                 or plain text like 'Login', 'Submit', 'Search'.
    Works with Indian language button/link text.
    """
    # Resolve ref
    el = _ref_map.get(ref_or_text)
    label_used = ref_or_text

    # If not a ref, search by label text in snapshot
    if el is None:
        query = ref_or_text.lower()
        for ref, info in _ref_map.items():
            if query in info.get("label", "").lower():
                el = info
                label_used = info.get("label", ref_or_text)
                break

    if el:
        # Click via JS using stored coordinates — reliable and instant
        x, y = el.get("x", 0), el.get("y", 0)
        try:
            # First try JS click (works even if element scrolled out of view)
            script = f"""
(function() {{
    var el = document.elementFromPoint({x}, {y});
    if (el) {{ el.click(); return 'clicked at ({x},{y})'; }}
    // Fallback: find by text
    var all = document.querySelectorAll('a,button,[role=button],[role=link],[role=menuitem],input[type=submit]');
    var q = {json.dumps(ref_or_text.lower())};
    for (var i=0; i<all.length; i++) {{
        var t = (all[i].innerText || all[i].value || all[i].getAttribute('aria-label') || '').toLowerCase();
        if (t.includes(q)) {{ all[i].click(); return 'text-match clicked: ' + all[i].innerText; }}
    }}
    return 'not found';
}})()
"""
            result = _js(script)
            if result and "not found" not in str(result):
                return f"Clicked '{label_used}'"
        except Exception:
            pass

        # CDP mouse event fallback (more reliable for some elements)
        try:
            _cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            _cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            return f"Clicked '{label_used}' at ({x}, {y})"
        except Exception as e:
            return f"Click failed: {e}. Try page_snapshot() to refresh element list."

    # No ref match — try pure JS text search
    try:
        script = f"""
(function() {{
    var q = {json.dumps(ref_or_text.toLowerCase() if hasattr(ref_or_text, 'toLowerCase') else ref_or_text.lower())};
    var candidates = document.querySelectorAll('a,button,[role=button],[role=link],[role=menuitem],input[type=submit],input[type=button],[onclick]');
    for (var i=0; i<candidates.length; i++) {{
        var t = (candidates[i].innerText || candidates[i].value || candidates[i].getAttribute('aria-label') || '').trim().toLowerCase();
        if (t === q || t.includes(q)) {{
            candidates[i].click();
            return 'Clicked: ' + (candidates[i].innerText || candidates[i].value || '').trim().slice(0,40);
        }}
    }}
    return null;
}})()
"""
        result = _js(script)
        if result:
            return result
        return (
            f"Could not find '{ref_or_text}' to click.\n"
            "Run page_snapshot() to see all clickable elements with refs."
        )
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Click failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Type into an input field
# ---------------------------------------------------------------------------

def _page_type(ref_or_text: str, text: str, clear_first: bool = True) -> str:
    """
    Type text into an input field on the page.
    ref_or_text: ref from page_snapshot() like 'e2',
                 or field label/placeholder like 'Search', 'Email', 'Password'.
    Handles Indian language text input correctly.
    """
    el = _ref_map.get(ref_or_text)
    label_used = ref_or_text

    if el is None:
        query = ref_or_text.lower()
        for ref, info in _ref_map.items():
            tag = info.get("tag", "")
            if tag in ("input", "textarea", "select") or info.get("role") in ("textbox", "searchbox", "combobox"):
                if query in info.get("label", "").lower():
                    el = info
                    label_used = info.get("label", ref_or_text)
                    break

    if el:
        x, y = el.get("x", 0), el.get("y", 0)
    else:
        x, y = 0, 0

    try:
        clear_js = "true" if clear_first else "false"
        escaped_text = json.dumps(text)
        script = f"""
(function() {{
    var el = null;
    // Try by position first
    if ({x} && {y}) el = document.elementFromPoint({x}, {y});

    // Fallback: find input by label/placeholder
    if (!el || !el.matches('input,textarea,select,[contenteditable]')) {{
        var q = {json.dumps(ref_or_text.lower())};
        var inputs = document.querySelectorAll('input,textarea,select,[contenteditable]');
        for (var i=0; i<inputs.length; i++) {{
            var t = (
                inputs[i].placeholder || inputs[i].getAttribute('aria-label') ||
                inputs[i].name || inputs[i].id || ''
            ).toLowerCase();
            if (t.includes(q)) {{ el = inputs[i]; break; }}
        }}
    }}

    if (!el) return 'field not found';

    el.focus();
    if ({clear_js}) {{
        el.select ? el.select() : null;
        el.value = '';
    }}

    // Set value and dispatch events so React/Vue/Angular detect the change
    var nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
    if (nativeInputSetter && el.tagName === 'INPUT') {{
        nativeInputSetter.set.call(el, {escaped_text});
    }} else {{
        el.value = {escaped_text};
    }}
    el.dispatchEvent(new Event('input', {{bubbles:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
    return 'typed: ' + {escaped_text}.slice(0,40);
}})()
"""
        result = _js(script)
        if result and "not found" not in str(result):
            return f"Typed into '{label_used}': {text[:50]}{'...' if len(text) > 50 else ''}"
        return (
            f"Field '{ref_or_text}' not found.\n"
            "Run page_snapshot() to see all input fields."
        )
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Type failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Press a key (Enter, Tab, Escape, etc.)
# ---------------------------------------------------------------------------

def _page_press_key(key: str) -> str:
    """
    Press a keyboard key on the focused element in the browser.
    key: 'Enter', 'Tab', 'Escape', 'ArrowDown', 'Backspace', etc.
    """
    try:
        _cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key})
        _cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key})
        return f"Pressed key: {key}"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Key press failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Scroll the page
# ---------------------------------------------------------------------------

def _page_scroll(direction: str = "down", amount: int = 400) -> str:
    """
    Scroll the current page up or down.
    direction: 'up' or 'down'
    amount: pixels to scroll (default 400)
    """
    delta = amount if direction == "down" else -amount
    try:
        _js(f"window.scrollBy(0, {delta})")
        return f"Scrolled {direction} {amount}px"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"Scroll failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Get current page info
# ---------------------------------------------------------------------------

def _page_info() -> str:
    """Get title, URL, and basic info about the current page."""
    try:
        title = _js("document.title") or ""
        url = _js("location.href") or ""
        ready = _js("document.readyState") or ""
        lang = _js("document.documentElement.lang") or "unknown"
        links = _js("document.querySelectorAll('a[href]').length") or 0
        inputs = _js("document.querySelectorAll('input,textarea,select').length") or 0
        buttons = _js("document.querySelectorAll('button,[role=button]').length") or 0

        return (
            f"Title:   {title}\n"
            f"URL:     {url}\n"
            f"State:   {ready}\n"
            f"Lang:    {lang}\n"
            f"Links:   {links}\n"
            f"Inputs:  {inputs}\n"
            f"Buttons: {buttons}\n\n"
            f"Use page_read() for full text, page_snapshot() for clickable elements."
        )
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"page_info failed: {e}"


# ---------------------------------------------------------------------------
# Tool: Run custom JavaScript
# ---------------------------------------------------------------------------

def _page_js(script: str) -> str:
    """
    Run custom JavaScript on the current page and return the result.
    Useful for reading specific data, clicking complex elements, etc.
    Example: page_js("document.querySelector('#result').innerText")
    """
    try:
        result = _js(script)
        return str(result) if result is not None else "(no return value)"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"
    except Exception as e:
        return f"JS execution failed: {e}"


# ---------------------------------------------------------------------------
# Tool: List all open tabs
# ---------------------------------------------------------------------------

def _page_list_tabs() -> str:
    """List all open tabs in the connected browser."""
    tabs = _get_tabs()
    if not tabs:
        return f"No browser found on port {_CDP_PORT}. Run browser_launch_debug() first."
    lines = [f"Open tabs ({len(tabs)}):"]
    for i, t in enumerate(tabs):
        title = t.get("title", "untitled")[:60]
        url = t.get("url", "")[:70]
        lines.append(f"  [{i}] {title}\n      {url}")
    lines.append("\nUse page_connect(tab_index=N) to switch tabs.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Wait for element to appear
# ---------------------------------------------------------------------------

def _page_wait_for(text: str, timeout: int = 10) -> str:
    """
    Wait until text appears on the page (polling DOM, not OCR).
    Useful after clicking buttons that trigger page updates.
    text: text to wait for on the page.
    timeout: max seconds to wait (default 10).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            found = _js(f"""document.body.innerText.toLowerCase().includes({json.dumps(text.lower())})""")
            if found:
                return f"Found '{text}' on page."
        except Exception:
            pass
        time.sleep(0.5)
    return f"'{text}' did not appear within {timeout} seconds."


# ---------------------------------------------------------------------------
# Tool: Go back / forward
# ---------------------------------------------------------------------------

def _page_back() -> str:
    """Go back in browser history."""
    try:
        _js("history.back()")
        time.sleep(0.5)
        _wait_for_load(max_wait=5.0)
        return f"Went back. Now on: {_js('document.title')}"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"


def _page_forward() -> str:
    """Go forward in browser history."""
    try:
        _js("history.forward()")
        time.sleep(0.5)
        _wait_for_load(max_wait=5.0)
        return f"Went forward. Now on: {_js('document.title')}"
    except RuntimeError as e:
        return f"Not connected. Run page_connect() first.\nDetail: {e}"


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

registry.register(
    "browser_launch_debug",
    "Launch Chrome/Edge/Brave with the remote debugging port so Parrrot can "
    "connect to your real browser (with your logins and sessions preserved). "
    "Automatically closes any running browser instance first so the debug port can be set.",
    {
        "browser": "chrome, edge, brave, or auto (default — tries all)",
        "close_existing": "close running browser first (default true, required for debug port)",
    },
)(_browser_launch_debug)

registry.register(
    "page_connect",
    "Connect to your running Chrome/Edge/Brave browser. Must run browser_launch_debug() first. "
    "Use tab_index to pick a specific tab.",
    {"tab_index": "which tab to connect (0=active, default)"},
)(_page_connect)

registry.register(
    "page_list_tabs",
    "List all open tabs in the connected browser with their titles and URLs.",
    {},
)(_page_list_tabs)

registry.register(
    "page_navigate",
    "Navigate the browser to a URL. Waits for page to load before returning.",
    {"url": "URL to navigate to", "wait_load": "wait for full load (default true)"},
)(_page_navigate)

registry.register(
    "page_read",
    "Read all text on the current page directly from the DOM — instant, no OCR. "
    "Works with ALL languages including Hindi, Tamil, Telugu, Malayalam, Bengali, etc.",
    {"max_chars": "max characters to return (default 6000)"},
)(_page_read)

registry.register(
    "page_snapshot",
    "Get all interactive elements on the current page with refs (e1, e2, ...). "
    "Lists every button, link, input, dropdown, checkbox. Works with Indian language pages. "
    "Use refs with page_click('e3') or page_type('e2', 'text').",
    {"include_text": "also include non-interactive text nodes (default false)"},
)(_page_snapshot)

registry.register(
    "page_click",
    "Click an element on the current page by ref (from page_snapshot) or by text. "
    "Example: page_click('e3') or page_click('Login') or page_click('लॉगिन').",
    {"ref_or_text": "ref like 'e3', or visible text of the element to click"},
)(_page_click)

registry.register(
    "page_type",
    "Type text into an input field on the current page. "
    "Use ref from page_snapshot() or field label/placeholder. "
    "Works with React/Vue/Angular apps (fires proper input events).",
    {
        "ref_or_text": "ref like 'e2' or field name/placeholder",
        "text": "text to type",
        "clear_first": "clear existing text first (default true)",
    },
)(_page_type)

registry.register(
    "page_press_key",
    "Press a keyboard key in the browser (Enter, Tab, Escape, ArrowDown, etc.)",
    {"key": "key name: Enter, Tab, Escape, ArrowDown, ArrowUp, Backspace, etc."},
)(_page_press_key)

registry.register(
    "page_scroll",
    "Scroll the current page up or down.",
    {"direction": "up or down (default: down)", "amount": "pixels to scroll (default: 400)"},
)(_page_scroll)

registry.register(
    "page_info",
    "Get title, URL, load state, language, and element counts for the current page.",
    {},
)(_page_info)

registry.register(
    "page_js",
    "Run custom JavaScript on the current page and return the result. "
    "Example: page_js(\"document.querySelector('#price').innerText\")",
    {"script": "JavaScript expression to evaluate"},
)(_page_js)

registry.register(
    "page_wait_for",
    "Wait until specific text appears on the page (polls DOM, not OCR). "
    "Use after clicking buttons that load new content.",
    {
        "text": "text to wait for on the page",
        "timeout": "max seconds to wait (default 10)",
    },
)(_page_wait_for)

registry.register(
    "page_back",
    "Go back in browser history.",
    {},
)(_page_back)

registry.register(
    "page_forward",
    "Go forward in browser history.",
    {},
)(_page_forward)
