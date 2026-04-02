"""
Parrrot — Firefox-first browser control.
Always uses Firefox. If Firefox is already open, opens a new tab.
If Firefox is not open, launches it. Never touches Chromium/Chrome/Edge.
Drives Firefox via keyboard shortcuts (Ctrl+L, Ctrl+T, etc.) — no Playwright.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Optional

from parrrot.tools.registry import registry

_SYSTEM = platform.system()
_DEFAULT_LOAD_WAIT = 3.5

# ---------------------------------------------------------------------------
# Find Firefox executable
# ---------------------------------------------------------------------------

_FIREFOX_EXE: Optional[str] = None   # cached after first find


def _find_firefox() -> Optional[str]:
    """Locate firefox.exe (Windows) or firefox (Linux/macOS). Returns path or None."""
    global _FIREFOX_EXE
    if _FIREFOX_EXE and os.path.isfile(_FIREFOX_EXE):
        return _FIREFOX_EXE

    import shutil

    # 1. Already on PATH
    found = shutil.which("firefox") or shutil.which("firefox.exe")
    if found:
        _FIREFOX_EXE = found
        return found

    if _SYSTEM == "Windows":
        candidates = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
        ]
        # Also try registry
        try:
            import winreg  # type: ignore[import]
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
            )
            val, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if val and os.path.isfile(val):
                _FIREFOX_EXE = val
                return val
        except Exception:
            pass
        for path in candidates:
            if os.path.isfile(path):
                _FIREFOX_EXE = path
                return path

    elif _SYSTEM == "Darwin":
        macos_path = "/Applications/Firefox.app/Contents/MacOS/firefox"
        if os.path.isfile(macos_path):
            _FIREFOX_EXE = macos_path
            return macos_path

    return None


def _firefox_not_found_msg() -> str:
    return (
        "Firefox not found.\n"
        "Install Firefox from https://www.mozilla.org/firefox\n"
        "or set the path in ~/.parrrot/config.toml:\n"
        "  [browser]\n"
        "  firefox_path = 'C:\\\\Program Files\\\\Mozilla Firefox\\\\firefox.exe'"
    )


# ---------------------------------------------------------------------------
# Firefox window detection
# ---------------------------------------------------------------------------

def _get_firefox_window():
    """Return the Firefox pyautogui window, or None."""
    try:
        import pyautogui
        for title_fragment in ("Mozilla Firefox", "Firefox"):
            wins = pyautogui.getWindowsWithTitle(title_fragment)
            if wins:
                return wins[0]
    except Exception:
        pass
    return None


def _is_firefox_running() -> bool:
    """Check if Firefox is currently running."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "firefox" in name:
                return True
    except Exception:
        pass
    # Fallback: check window title
    return _get_firefox_window() is not None


def _focus_firefox(wait: float = 0.4) -> bool:
    """Bring Firefox to the foreground. Returns True if successful."""
    win = _get_firefox_window()
    if win:
        try:
            win.restore()   # un-minimize if needed
            win.activate()
            time.sleep(wait)
            return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Open URL in Firefox — new tab if running, new window if not
# ---------------------------------------------------------------------------

def _open_in_firefox(url: str, new_tab: bool = True, wait: float = _DEFAULT_LOAD_WAIT) -> str:
    """
    Open a URL in Firefox.
    - If Firefox is already open → opens in a new tab (--new-tab flag)
    - If Firefox is not open     → launches Firefox and opens the URL
    Never opens Chromium, Chrome, Edge, or any other browser.
    """
    fx = _find_firefox()
    if not fx:
        return _firefox_not_found_msg()

    already_running = _is_firefox_running()

    if already_running and new_tab:
        # --new-tab opens in the existing Firefox instance
        subprocess.Popen([fx, "--new-tab", url])
    else:
        subprocess.Popen([fx, url])

    time.sleep(1.5)  # give Firefox time to process the command
    _focus_firefox(wait=0.5)
    time.sleep(wait)  # wait for page to load

    action = "new tab" if (already_running and new_tab) else "new window"
    return f"Opened in Firefox ({action}): {url}"


# ---------------------------------------------------------------------------
# Navigate to URL — uses address bar if Firefox is focused, new tab otherwise
# ---------------------------------------------------------------------------

def _navigate_to(url: str, wait: float = _DEFAULT_LOAD_WAIT) -> str:
    """
    Navigate Firefox to a URL.
    If Firefox is open and focused → uses Ctrl+L (address bar navigation).
    If Firefox is not open         → launches it with the URL.
    Always Firefox. Never any other browser.
    """
    try:
        import pyautogui
    except ImportError:
        return "pyautogui not installed: pip install pyautogui"

    # Ensure scheme
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url

    # Make sure Firefox is open and focused
    if not _is_firefox_running():
        return _open_in_firefox(url, new_tab=False, wait=wait)

    focused = _focus_firefox(wait=0.3)
    if not focused:
        return _open_in_firefox(url, new_tab=True, wait=wait)

    # Ctrl+L → focus the Firefox address bar
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.35)

    # Select all + paste URL (clipboard method handles all chars reliably)
    try:
        import pyperclip
        old_clip = pyperclip.paste()
        pyperclip.copy(url)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(wait)
        try:
            pyperclip.copy(old_clip)   # restore clipboard
        except Exception:
            pass
    except ImportError:
        # typewrite fallback (ASCII only)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.typewrite(url, interval=0.025)
        pyautogui.press("enter")
        time.sleep(wait)

    return f"Navigated Firefox to: {url}"


# ---------------------------------------------------------------------------
# New tab
# ---------------------------------------------------------------------------

def _open_new_tab(url: str = "", wait: float = _DEFAULT_LOAD_WAIT) -> str:
    """Open a new tab in Firefox. If a URL is given, navigate to it."""
    fx = _find_firefox()
    if not fx:
        return _firefox_not_found_msg()

    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if _is_firefox_running():
            subprocess.Popen([fx, "--new-tab", url])
            time.sleep(1.2)
            _focus_firefox(wait=0.4)
            time.sleep(wait)
            return f"New Firefox tab opened: {url}"
        else:
            return _open_in_firefox(url, new_tab=False, wait=wait)

    # Just open an empty new tab with Ctrl+T
    if _is_firefox_running():
        _focus_firefox(wait=0.3)
        try:
            import pyautogui
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.4)
        except ImportError:
            pass
        return "New empty tab opened in Firefox"
    return _open_in_firefox("about:newtab", new_tab=False, wait=1.0)


# ---------------------------------------------------------------------------
# Navigation controls (all Firefox-specific)
# ---------------------------------------------------------------------------

def _browser_back() -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        pyautogui.hotkey("alt", "left")
        time.sleep(0.8)
        return "Firefox: navigated back"
    except ImportError:
        return "pyautogui not installed."


def _browser_forward() -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        pyautogui.hotkey("alt", "right")
        time.sleep(0.8)
        return "Firefox: navigated forward"
    except ImportError:
        return "pyautogui not installed."


def _browser_refresh(hard: bool = False) -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "shift", "r") if hard else pyautogui.press("f5")
        time.sleep(1.5)
        return f"Firefox: {'hard' if hard else 'soft'} refresh"
    except ImportError:
        return "pyautogui not installed."


def _browser_close_tab() -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "w")
        time.sleep(0.3)
        return "Firefox: closed current tab"
    except ImportError:
        return "pyautogui not installed."


def _browser_zoom(direction: str = "in", steps: int = 1) -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        if direction == "reset":
            pyautogui.hotkey("ctrl", "0")
            return "Firefox: zoom reset to 100%"
        key = "=" if direction == "in" else "-"
        for _ in range(steps):
            pyautogui.hotkey("ctrl", key)
            time.sleep(0.1)
        return f"Firefox: zoomed {direction} {steps} step(s)"
    except ImportError:
        return "pyautogui not installed."


def _browser_find(text: str) -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.3)
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(text, interval=0.04)
        return f"Firefox find-bar: searching for '{text}'"
    except ImportError:
        return "pyautogui not installed."


def _browser_scroll(direction: str = "down", amount: int = 5) -> str:
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui
        w, h = pyautogui.size()
        pyautogui.click(w // 2, h // 2)
        time.sleep(0.1)
        pyautogui.scroll(-amount if direction == "down" else amount)
        return f"Firefox: scrolled {direction}"
    except ImportError:
        return "pyautogui not installed."


def _get_current_url() -> str:
    """Read the URL from the Firefox address bar via clipboard."""
    if not _focus_firefox(0.2):
        return "Firefox is not open."
    try:
        import pyautogui, pyperclip
        old = pyperclip.paste()
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.25)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        pyautogui.press("escape")
        url = pyperclip.paste()
        pyperclip.copy(old)
        return f"Current Firefox URL: {url}"
    except ImportError:
        return "pyperclip not installed: pip install pyperclip"


def _browser_screenshot_and_read() -> str:
    """Screenshot Firefox and OCR all visible text."""
    if not _focus_firefox(0.3):
        return "Firefox is not open."
    time.sleep(0.4)
    from parrrot.tools.screen import _ocr_screen
    text = _ocr_screen()
    return f"Firefox page content (Tesseract OCR):\n\n{text[:5000]}" if text else (
        "No text detected. Make sure Tesseract is installed:\n"
        "  https://github.com/UB-Mannheim/tesseract/wiki"
    )


def _web_search(query: str, engine: str = "google") -> str:
    """Open a web search in Firefox."""
    urls = {
        "google":     f"https://www.google.com/search?q={query.replace(' ', '+')}",
        "duckduckgo": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
        "bing":       f"https://www.bing.com/search?q={query.replace(' ', '+')}",
        "youtube":    f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
    }
    url = urls.get(engine.lower(), urls["google"])
    result = _navigate_to(url, wait=3.0)
    return f"Searching Firefox for '{query}' on {engine}\n{result}"


def _open_url(url: str, wait: float = _DEFAULT_LOAD_WAIT) -> str:
    """Open a URL in Firefox (new tab if already open)."""
    return _open_in_firefox(url, new_tab=True, wait=wait)


def _get_firefox_status() -> str:
    """Report whether Firefox is running and what path was found."""
    fx = _find_firefox()
    running = _is_firefox_running()
    win = _get_firefox_window()
    lines = [
        f"Firefox path:    {fx or 'NOT FOUND'}",
        f"Firefox running: {'yes' if running else 'no'}",
        f"Window title:    {win.title if win else 'N/A'}",
    ]
    if not fx:
        lines.append("\nInstall Firefox: https://www.mozilla.org/firefox")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "open_url",
    "Open a URL in Firefox — new tab if Firefox is already open, new window if not",
    {"url": "URL to open", "wait": "seconds to wait for load (default 3.5)"},
)(_open_url)

registry.register(
    "navigate_to",
    "Navigate Firefox to a URL using the address bar (Ctrl+L). Always uses Firefox.",
    {"url": "URL to navigate to", "wait": "seconds to wait for page load (default 3.5)"},
)(_navigate_to)

registry.register(
    "web_search",
    "Open a web search in Firefox (Google/DuckDuckGo/Bing/YouTube)",
    {"query": "what to search for", "engine": "google (default), duckduckgo, bing, youtube"},
)(_web_search)

registry.register(
    "open_new_tab",
    "Open a new tab in Firefox, optionally navigate to a URL",
    {"url": "optional URL", "wait": "seconds to wait for load (default 3.5)"},
)(_open_new_tab)

registry.register(
    "browser_back",   "Go back in Firefox history",             {})(_browser_back)
registry.register(
    "browser_forward","Go forward in Firefox history",          {})(_browser_forward)
registry.register(
    "browser_refresh","Refresh current Firefox page",           {"hard": "true for hard reload"})(_browser_refresh)
registry.register(
    "browser_close_tab","Close the current Firefox tab",        {})(_browser_close_tab)
registry.register(
    "browser_zoom",   "Zoom Firefox page in/out/reset",         {"direction": "in/out/reset", "steps": "zoom steps (default 1)"})(_browser_zoom)
registry.register(
    "browser_find",   "Firefox Ctrl+F find-in-page",            {"text": "text to find"})(_browser_find)
registry.register(
    "browser_scroll", "Scroll the Firefox page",                {"direction": "up/down", "amount": "steps (default 5)"})(_browser_scroll)
registry.register(
    "get_current_url","Read the URL in the Firefox address bar",{})(_get_current_url)
registry.register(
    "browser_read_page","Tesseract-OCR the current Firefox page","")(_browser_screenshot_and_read)
registry.register(
    "firefox_status", "Check if Firefox is installed and running","")(_get_firefox_status)
