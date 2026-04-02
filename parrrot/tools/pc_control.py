"""
Parrrot — Mouse, keyboard, and window control tools.
Includes visual_click / visual_type which combine screen vision + pyautogui
so the agent can say "click the Compose button" without knowing coordinates.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import time
from typing import Optional

from parrrot.tools.registry import registry

_PYAUTOGUI_MSG = "PC control requires pyautogui. Install: pip install pyautogui"


def _move_mouse(x: int, y: int) -> str:
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.3)
        return f"Mouse moved to ({x}, {y})"
    except ImportError:
        return _PYAUTOGUI_MSG


def _click(x: int, y: int, button: str = "left") -> str:
    try:
        import pyautogui
        pyautogui.click(x, y, button=button)
        return f"Clicked {button} at ({x}, {y})"
    except ImportError:
        return _PYAUTOGUI_MSG


def _double_click(x: int, y: int) -> str:
    try:
        import pyautogui
        pyautogui.doubleClick(x, y)
        return f"Double-clicked at ({x}, {y})"
    except ImportError:
        return _PYAUTOGUI_MSG


def _type_text(text: str, interval: float = 0.02) -> str:
    try:
        import pyautogui
        pyautogui.typewrite(text, interval=interval)
        return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"
    except ImportError:
        return _PYAUTOGUI_MSG


def _press_key(key: str) -> str:
    try:
        import pyautogui
        pyautogui.press(key)
        return f"Pressed key: {key}"
    except ImportError:
        return _PYAUTOGUI_MSG


def _hotkey(*keys: str) -> str:
    try:
        import pyautogui
        pyautogui.hotkey(*keys)
        return f"Hotkey: {'+'.join(keys)}"
    except ImportError:
        return _PYAUTOGUI_MSG


def _hotkey_tool(keys: list[str]) -> str:
    return _hotkey(*keys)


def _scroll(direction: str = "down", amount: int = 3) -> str:
    try:
        import pyautogui
        clicks = amount if direction == "down" else -amount
        pyautogui.scroll(clicks)
        return f"Scrolled {direction} {amount} clicks"
    except ImportError:
        return _PYAUTOGUI_MSG


def _drag(start: list[int], end: list[int], duration: float = 0.5) -> str:
    """Drag from start [x,y] to end [x,y]."""
    try:
        import pyautogui
        pyautogui.moveTo(start[0], start[1])
        pyautogui.dragTo(end[0], end[1], duration=duration, button="left")
        return f"Dragged from {start} to {end}"
    except ImportError:
        return _PYAUTOGUI_MSG


def _get_window_list() -> str:
    try:
        import pyautogui
        windows = pyautogui.getAllWindows()
        if not windows:
            return "No windows found."
        lines = [f"• {w.title} ({w.width}x{w.height} at {w.left},{w.top})" for w in windows if w.title]
        return "\n".join(lines[:30]) or "No titled windows found."
    except ImportError:
        return _PYAUTOGUI_MSG
    except AttributeError:
        # pyautogui.getAllWindows() only works on some platforms
        return "Window list not available on this platform."


def _focus_window(title: str) -> str:
    try:
        import pyautogui
        windows = pyautogui.getWindowsWithTitle(title)
        if not windows:
            return f"No window found with title containing '{title}'"
        windows[0].activate()
        return f"Focused window: {windows[0].title}"
    except ImportError:
        return _PYAUTOGUI_MSG
    except Exception as e:
        return f"Could not focus window: {e}"


def _get_screen_size() -> str:
    try:
        import pyautogui
        w, h = pyautogui.size()
        return f"Screen size: {w}x{h} pixels"
    except ImportError:
        return _PYAUTOGUI_MSG


def _get_mouse_position() -> str:
    try:
        import pyautogui
        x, y = pyautogui.position()
        return f"Mouse position: ({x}, {y})"
    except ImportError:
        return _PYAUTOGUI_MSG


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register("move_mouse", "Move mouse cursor to position", {"x": "x coordinate", "y": "y coordinate"})(_move_mouse)
registry.register("click", "Click at pixel coordinates", {"x": "x", "y": "y", "button": "left/right/middle"})(_click)
registry.register("double_click", "Double-click at pixel coordinates", {"x": "x", "y": "y"})(_double_click)
registry.register("type_text", "Type text at the current cursor position", {"text": "text to type", "interval": "seconds between keystrokes (default 0.02)"})(_type_text)
registry.register("press_key", "Press a keyboard key (e.g. 'enter', 'tab', 'escape', 'f5')", {"key": "key name"})(_press_key)
registry.register("hotkey", "Press a keyboard shortcut (e.g. ctrl+c)", {"keys": "list of keys, e.g. ['ctrl', 'c']"})(_hotkey_tool)
registry.register("scroll", "Scroll the mouse wheel", {"direction": "up or down", "amount": "number of clicks (default 3)"})(_scroll)
registry.register("drag", "Drag from one position to another", {"start": "[x, y] start position", "end": "[x, y] end position"})(_drag)
registry.register("get_window_list", "List all open windows", {})(_get_window_list)
registry.register("focus_window", "Bring a window to the foreground by title", {"title": "window title (partial match)"})(_focus_window)
registry.register("get_screen_size", "Get screen resolution", {})(_get_screen_size)
registry.register("get_mouse_position", "Get current mouse cursor position", {})(_get_mouse_position)


# ---------------------------------------------------------------------------
# Vision-guided controls — find element by description, then act on it
# These are the high-level "Jarvis" actions that use the screen vision loop.
# ---------------------------------------------------------------------------

async def _visual_click(description: str, button: str = "left", double: bool = False) -> str:
    """
    Look at the screen, find the described element using the vision model,
    then click it. No coordinates needed — just describe what to click.

    Examples:
        visual_click("Compose button")
        visual_click("Search bar in Gmail")
        visual_click("Send button", double=False)
    """
    from parrrot.tools.screen import find_element_coords

    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    coords = await find_element_coords(description)
    if coords is None:
        return (
            f"Could not find '{description}' on screen. "
            f"Try: take_screenshot + ask_screen to confirm it's visible."
        )

    x, y = coords
    pyautogui.moveTo(x, y, duration=0.25)
    time.sleep(0.1)
    if double:
        pyautogui.doubleClick(x, y, button=button)
        return f"Double-clicked '{description}' at ({x}, {y})"
    else:
        pyautogui.click(x, y, button=button)
        return f"Clicked '{description}' at ({x}, {y})"


async def _visual_type(field_description: str, text: str, clear_first: bool = True) -> str:
    """
    Find a text field by description, click it, optionally clear it, then type text.

    Examples:
        visual_type("To: field in Gmail compose", "friend@gmail.com")
        visual_type("Subject field", "Meeting tomorrow")
        visual_type("browser address bar", "https://gmail.com")
    """
    from parrrot.tools.screen import find_element_coords

    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    coords = await find_element_coords(field_description)
    if coords is None:
        return f"Could not find '{field_description}' on screen."

    x, y = coords
    pyautogui.click(x, y)
    time.sleep(0.2)

    if clear_first:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("delete")
        time.sleep(0.1)

    # Use pyperclip for reliable unicode typing if available, else typewrite
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    except ImportError:
        pyautogui.typewrite(text, interval=0.03)

    return f"Typed into '{field_description}': {text[:60]}{'...' if len(text) > 60 else ''}"


async def _visual_right_click(description: str) -> str:
    """Right-click on a described element."""
    return await _visual_click(description, button="right")


async def _visual_double_click(description: str) -> str:
    """Double-click on a described element."""
    return await _visual_click(description, double=True)


registry.register(
    "visual_click",
    "Look at the screen, find a UI element by description, and click it — no coordinates needed",
    {
        "description": "describe what to click, e.g. 'Compose button', 'Send button', 'inbox link'",
        "button": "mouse button: left (default), right, middle",
        "double": "true for double-click (default false)",
    },
)(_visual_click)

registry.register(
    "visual_type",
    "Find a text field on screen by description, click it, and type text into it",
    {
        "field_description": "describe the field, e.g. 'To: field', 'Subject line', 'address bar'",
        "text": "text to type",
        "clear_first": "clear existing content first (default true)",
    },
)(_visual_type)

registry.register(
    "visual_right_click",
    "Right-click on a described screen element",
    {"description": "describe what to right-click"},
)(_visual_right_click)

registry.register(
    "visual_double_click",
    "Double-click on a described screen element",
    {"description": "describe what to double-click"},
)(_visual_double_click)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def _clipboard_write(text: str) -> str:
    """Copy text to the clipboard."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return f"Copied to clipboard ({len(text)} chars)"
    except ImportError:
        # Fallback: PowerShell on Windows
        import platform, subprocess
        if platform.system() == "Windows":
            subprocess.run(
                ["powershell", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)*2)}'"],
                capture_output=True,
            )
            return f"Copied to clipboard via PowerShell ({len(text)} chars)"
        return "Clipboard write requires pyperclip: pip install pyperclip"


def _clipboard_read() -> str:
    """Read the current clipboard content."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return f"Clipboard contents:\n{text}" if text else "(clipboard is empty)"
    except ImportError:
        import platform, subprocess
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True, text=True,
            )
            return f"Clipboard:\n{result.stdout.strip()}" if result.stdout else "(empty)"
        return "Clipboard read requires pyperclip: pip install pyperclip"


def _clipboard_paste_at_cursor() -> str:
    """Paste clipboard content at the current cursor position (Ctrl+V)."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "v")
        return "Pasted clipboard at cursor"
    except ImportError:
        return _PYAUTOGUI_MSG


registry.register(
    "clipboard_write",
    "Copy text to the clipboard",
    {"text": "text to put in clipboard"},
)(_clipboard_write)

registry.register(
    "clipboard_read",
    "Read the current clipboard content",
    {},
)(_clipboard_read)

registry.register(
    "clipboard_paste",
    "Paste clipboard content at the current cursor position",
    {},
)(_clipboard_paste_at_cursor)


# ---------------------------------------------------------------------------
# Active window
# ---------------------------------------------------------------------------

def _get_active_window() -> str:
    """Return the title of the currently focused window."""
    try:
        import pyautogui
        win = pyautogui.getActiveWindow()
        if win:
            return (
                f"Active window: {win.title}\n"
                f"Size: {win.width}x{win.height}\n"
                f"Position: ({win.left}, {win.top})"
            )
        return "No active window detected."
    except ImportError:
        return _PYAUTOGUI_MSG
    except Exception as e:
        return f"Could not get active window: {e}"


def _bring_window_to_front(title: str) -> str:
    """Find a window by title fragment and bring it to the foreground."""
    try:
        import pyautogui
        windows = pyautogui.getWindowsWithTitle(title)
        if not windows:
            return f"No window found with title containing '{title}'"
        win = windows[0]
        win.activate()
        time.sleep(0.3)
        return f"Brought to front: {win.title}"
    except ImportError:
        return _PYAUTOGUI_MSG
    except Exception as e:
        return f"Could not focus window: {e}"


def _minimize_window(title: str = "") -> str:
    """Minimize a window by title, or the active window if no title given."""
    try:
        import pyautogui
        if title:
            windows = pyautogui.getWindowsWithTitle(title)
            win = windows[0] if windows else None
        else:
            win = pyautogui.getActiveWindow()
        if win:
            win.minimize()
            return f"Minimized: {win.title}"
        return "No window found to minimize."
    except ImportError:
        return _PYAUTOGUI_MSG
    except Exception as e:
        return f"Could not minimize: {e}"


def _maximize_window(title: str = "") -> str:
    """Maximize a window by title, or the active window if no title given."""
    try:
        import pyautogui
        if title:
            windows = pyautogui.getWindowsWithTitle(title)
            win = windows[0] if windows else None
        else:
            win = pyautogui.getActiveWindow()
        if win:
            win.maximize()
            return f"Maximized: {win.title}"
        return "No window found to maximize."
    except ImportError:
        return _PYAUTOGUI_MSG
    except Exception as e:
        return f"Could not maximize: {e}"


registry.register(
    "get_active_window",
    "Get the title and info of the currently focused window",
    {},
)(_get_active_window)

registry.register(
    "bring_window_to_front",
    "Find a window by title and bring it to the foreground",
    {"title": "window title fragment to search for"},
)(_bring_window_to_front)

registry.register(
    "minimize_window",
    "Minimize a window (by title, or the active window if no title given)",
    {"title": "optional window title fragment"},
)(_minimize_window)

registry.register(
    "maximize_window",
    "Maximize a window (by title, or the active window if no title given)",
    {"title": "optional window title fragment"},
)(_maximize_window)


# ---------------------------------------------------------------------------
# Volume control (Windows/macOS/Linux)
# ---------------------------------------------------------------------------

def _set_volume(level: int) -> str:
    """
    Set the system volume. level = 0-100.
    Windows: uses PowerShell / nircmd.
    macOS: uses osascript.
    Linux: uses amixer / pactl.
    """
    import platform as _pl
    level = max(0, min(100, level))
    sys = _pl.system()

    if sys == "Windows":
        # PowerShell method — works on all Windows 10/11
        import subprocess
        ps = f"""
$obj = New-Object -ComObject WScript.Shell
$wshShell = New-Object -ComObject WScript.Shell
(New-Object -ComObject Shell.Application).NameSpace('shell:AppsFolder').ParseName('Microsoft.Windows.Volume').InvokeVerbEx('Open')
"""
        # Simpler: use nircmd if available, else PowerShell audio
        try:
            result = subprocess.run(
                ["nircmd", "setsysvolume", str(int(level * 655.35))],
                capture_output=True, timeout=3,
            )
            if result.returncode == 0:
                return f"Volume set to {level}%"
        except FileNotFoundError:
            pass

        # PowerShell fallback via Windows Audio API
        ps_script = f"""
$obj = New-Object -ComObject WScript.Shell
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
    int f(); int g(); int h(); int i();
    int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);
    int j();
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int k(); int l(); int m(); int n();
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, System.Guid pguidEventContext);
    int GetMute(out bool pbMute);
}}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {{
    int Activate(ref System.Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev);
}}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {{
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject {{ }}
public class Audio {{
    static IAudioEndpointVolume Vol() {{
        var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
        IMMDevice dev = null;
        Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0, 1, out dev));
        IAudioEndpointVolume epv = null;
        var epvid = typeof(IAudioEndpointVolume).GUID;
        Marshal.ThrowExceptionForHR(dev.Activate(ref epvid, 23, 0, out epv));
        return epv;
    }}
    public static float Volume {{
        get {{ float v = -1; Marshal.ThrowExceptionForHR(Vol().GetMasterVolumeLevelScalar(out v)); return v; }}
        set {{ Marshal.ThrowExceptionForHR(Vol().SetMasterVolumeLevelScalar(value, System.Guid.Empty)); }}
    }}
    public static bool Mute {{
        get {{ bool mute; Marshal.ThrowExceptionForHR(Vol().GetMute(out mute)); return mute; }}
        set {{ Marshal.ThrowExceptionForHR(Vol().SetMute(value, System.Guid.Empty)); }}
    }}
}}
'@
[Audio]::Volume = {level / 100.0}
"""
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return f"Volume set to {level}%"
        return f"Volume control failed on Windows. Install nircmd for reliable volume control."

    elif sys == "Darwin":
        import subprocess
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], capture_output=True)
        return f"Volume set to {level}%"

    else:  # Linux
        import subprocess
        subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"], capture_output=True)
        return f"Volume set to {level}%"


def _mute_volume() -> str:
    """Mute the system volume."""
    try:
        import pyautogui
        pyautogui.press("volumemute")
        return "Volume muted"
    except ImportError:
        return _PYAUTOGUI_MSG


def _volume_up(steps: int = 5) -> str:
    """Increase system volume by pressing the volume-up key."""
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press("volumeup")
            time.sleep(0.05)
        return f"Volume increased by {steps} steps"
    except ImportError:
        return _PYAUTOGUI_MSG


def _volume_down(steps: int = 5) -> str:
    """Decrease system volume by pressing the volume-down key."""
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press("volumedown")
            time.sleep(0.05)
        return f"Volume decreased by {steps} steps"
    except ImportError:
        return _PYAUTOGUI_MSG


registry.register(
    "set_volume",
    "Set the system volume to a specific level (0-100)",
    {"level": "volume level 0-100"},
)(_set_volume)

registry.register(
    "mute_volume",
    "Toggle mute on the system audio",
    {},
)(_mute_volume)

registry.register(
    "volume_up",
    "Increase system volume",
    {"steps": "how many steps to increase (default 5)"},
)(_volume_up)

registry.register(
    "volume_down",
    "Decrease system volume",
    {"steps": "how many steps to decrease (default 5)"},
)(_volume_down)


# ---------------------------------------------------------------------------
# App launcher
# ---------------------------------------------------------------------------

def _launch_app(app_name: str) -> str:
    """
    Launch an application by name. Tries multiple methods.
    On Windows: Start menu search, then direct path.
    """
    import platform as _pl
    import subprocess, os

    sys = _pl.system()

    if sys == "Windows":
        # Method 1: Windows Run dialog (Win+R)
        try:
            import pyautogui
            pyautogui.hotkey("win", "r")
            time.sleep(0.5)
            try:
                import pyperclip
                pyperclip.copy(app_name)
                pyautogui.hotkey("ctrl", "v")
            except ImportError:
                pyautogui.typewrite(app_name, interval=0.05)
            time.sleep(0.2)
            pyautogui.press("enter")
            return f"Launched via Run: {app_name}"
        except Exception:
            pass

        # Method 2: subprocess
        try:
            subprocess.Popen(app_name, shell=True)
            return f"Launched: {app_name}"
        except Exception as e:
            return f"Could not launch '{app_name}': {e}"

    elif sys == "Darwin":
        try:
            subprocess.Popen(["open", "-a", app_name])
            return f"Launched: {app_name}"
        except Exception as e:
            return f"Could not launch '{app_name}': {e}"

    else:
        try:
            subprocess.Popen([app_name])
            return f"Launched: {app_name}"
        except Exception as e:
            return f"Could not launch '{app_name}': {e}"


def _open_file_manager(path: str = "") -> str:
    """Open the file manager (Explorer/Finder/Nautilus) at an optional path."""
    import platform as _pl, subprocess, os
    sys = _pl.system()
    target = os.path.expanduser(path) if path else os.path.expanduser("~")

    if sys == "Windows":
        subprocess.Popen(["explorer", target])
    elif sys == "Darwin":
        subprocess.Popen(["open", target])
    else:
        for fm in ["nautilus", "thunar", "nemo", "dolphin", "pcmanfm"]:
            try:
                subprocess.Popen([fm, target])
                return f"Opened file manager at: {target}"
            except FileNotFoundError:
                continue
        return "No file manager found."
    return f"Opened file manager at: {target}"


registry.register(
    "launch_app",
    "Launch an application by name (e.g. 'notepad', 'calc', 'spotify', 'vscode')",
    {"app_name": "application name or executable"},
)(_launch_app)

registry.register(
    "open_file_manager",
    "Open the file manager (Explorer on Windows) at an optional folder path",
    {"path": "optional folder path to open (default: home folder)"},
)(_open_file_manager)


# ---------------------------------------------------------------------------
# Smart navigation — OCR + keyboard shortcuts, no vision model needed
# ---------------------------------------------------------------------------

def _search_open(query: str) -> str:
    """
    Open an app or file by searching for it via the Windows Start menu / Spotlight / launcher.
    Windows: presses Win key, types the name, waits for results, presses Enter.
    macOS: uses Spotlight (Cmd+Space).
    Linux: tries common launchers (rofi, dmenu, krunner).
    """
    import platform as _pl
    sys = _pl.system()

    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    if sys == "Windows":
        pyautogui.press("win")
        time.sleep(0.8)  # wait for Start menu
        try:
            import pyperclip
            pyperclip.copy(query)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(query, interval=0.06)
        time.sleep(1.5)  # wait for search results
        pyautogui.press("enter")
        time.sleep(0.5)
        return f"Searched and opened: {query}"

    elif sys == "Darwin":
        pyautogui.hotkey("cmd", "space")
        time.sleep(0.5)
        try:
            import pyperclip
            pyperclip.copy(query)
            pyautogui.hotkey("cmd", "v")
        except ImportError:
            pyautogui.typewrite(query, interval=0.06)
        time.sleep(1.0)
        pyautogui.press("enter")
        return f"Opened via Spotlight: {query}"

    else:
        for launcher_combo in [("ctrl", "f2"), ("super",)]:
            try:
                pyautogui.hotkey(*launcher_combo)
                time.sleep(0.5)
                pyautogui.typewrite(query, interval=0.06)
                time.sleep(0.8)
                pyautogui.press("enter")
                return f"Opened via launcher: {query}"
            except Exception:
                continue
        return f"Could not find launcher. Try launch_app('{query}') instead."


def _ocr_click(text: str, partial: bool = True) -> str:
    """
    Find text on screen via Tesseract OCR and click it. No vision model needed.
    partial=True allows partial/fuzzy matching (default).
    This is the most reliable way to click UI elements with a text-only model.
    """
    from parrrot.tools.screen import _ocr_find_text_coords, capture_screen

    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    path = capture_screen()
    if path.startswith("Screen capture"):
        return "Could not capture screen."

    coords = _ocr_find_text_coords(text, path)
    if coords is None:
        return (
            f"Could not find '{text}' on screen via OCR. "
            f"Try read_screen_text to see what text is currently visible."
        )

    x, y = coords
    pyautogui.moveTo(x, y, duration=0.2)
    time.sleep(0.1)
    pyautogui.click(x, y)
    return f"OCR-clicked '{text}' at ({x}, {y})"


def _tab_click(tab_index: int = 1) -> str:
    """Press Tab N times then Enter to activate a focused element. Useful for keyboard navigation."""
    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    for _ in range(tab_index):
        pyautogui.press("tab")
        time.sleep(0.08)
    pyautogui.press("enter")
    return f"Pressed Tab x{tab_index} then Enter"


def _keyboard_navigate(action: str) -> str:
    """
    Smart keyboard navigation shortcuts.
    action can be:
      - "address_bar"        → Ctrl+L (browser/explorer address bar)
      - "new_tab"            → Ctrl+T
      - "close_tab"          → Ctrl+W
      - "reopen_tab"         → Ctrl+Shift+T
      - "save"               → Ctrl+S
      - "select_all"         → Ctrl+A
      - "copy"               → Ctrl+C
      - "paste"              → Ctrl+V
      - "cut"                → Ctrl+X
      - "undo"               → Ctrl+Z
      - "redo"               → Ctrl+Y
      - "find"               → Ctrl+F
      - "refresh"            → F5
      - "fullscreen"         → F11
      - "zoom_in"            → Ctrl+=
      - "zoom_out"           → Ctrl+-
      - "zoom_reset"         → Ctrl+0
      - "back"               → Alt+Left
      - "forward"            → Alt+Right
      - "close_window"       → Alt+F4
      - "switch_window"      → Alt+Tab
      - "desktop"            → Win+D
      - "task_manager"       → Ctrl+Shift+Esc
      - "settings"           → Win+I (Windows)
      - "file_explorer"      → Win+E (Windows)
      - "lock_screen"        → Win+L (Windows)
      - "screenshot"         → Win+Shift+S (Windows snip)
      - "run_dialog"         → Win+R (Windows)
    """
    import platform as _pl
    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    sys = _pl.system()
    action = action.lower().strip()

    shortcuts: dict[str, tuple] = {
        "address_bar":    ("ctrl", "l"),
        "new_tab":        ("ctrl", "t"),
        "close_tab":      ("ctrl", "w"),
        "reopen_tab":     ("ctrl", "shift", "t"),
        "save":           ("ctrl", "s"),
        "select_all":     ("ctrl", "a"),
        "copy":           ("ctrl", "c"),
        "paste":          ("ctrl", "v"),
        "cut":            ("ctrl", "x"),
        "undo":           ("ctrl", "z"),
        "redo":           ("ctrl", "y"),
        "find":           ("ctrl", "f"),
        "refresh":        ("f5",),
        "fullscreen":     ("f11",),
        "zoom_in":        ("ctrl", "="),
        "zoom_out":       ("ctrl", "-"),
        "zoom_reset":     ("ctrl", "0"),
        "back":           ("alt", "left"),
        "forward":        ("alt", "right"),
        "close_window":   ("alt", "f4"),
        "switch_window":  ("alt", "tab"),
        "desktop":        ("win", "d"),
        "task_manager":   ("ctrl", "shift", "escape"),
        "settings":       ("win", "i"),
        "file_explorer":  ("win", "e"),
        "lock_screen":    ("win", "l"),
        "screenshot":     ("win", "shift", "s"),
        "run_dialog":     ("win", "r"),
    }

    if action not in shortcuts:
        available = ", ".join(sorted(shortcuts.keys()))
        return f"Unknown action '{action}'. Available: {available}"

    keys = shortcuts[action]
    pyautogui.hotkey(*keys)
    time.sleep(0.3)
    return f"Keyboard shortcut executed: {action} ({'+'.join(keys)})"


def _type_paste(text: str) -> str:
    """
    Type text at the current cursor using clipboard paste.
    More reliable than typewrite — handles Unicode, long text, special chars.
    """
    try:
        import pyautogui
    except ImportError:
        return _PYAUTOGUI_MSG

    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return f"Pasted text ({len(text)} chars)"
    except ImportError:
        # ASCII fallback
        pyautogui.typewrite(text[:500], interval=0.02)
        return f"Typed text ({min(len(text), 500)} chars)"


async def _smart_click(description: str) -> str:
    """
    Click a UI element by description. Uses OCR as primary method (no vision model needed).
    For text-based elements (buttons, menus, links): OCR finds them directly.
    Falls back to vision LLM if OCR can't locate the element.
    """
    # Try OCR click first
    result = _ocr_click(description)
    if "OCR-clicked" in result:
        return result

    # OCR didn't find it — try vision-based visual_click
    return await _visual_click(description)


registry.register(
    "search_open",
    "Open an app or file by searching for it (Windows Start menu / Spotlight). "
    "More reliable than launch_app for apps without a direct executable name.",
    {"query": "app name or file to open, e.g. 'Spotify', 'Visual Studio Code', 'Settings'"},
)(_search_open)

registry.register(
    "ocr_click",
    "Find text on screen using OCR and click it — works without a vision model. "
    "Best for clicking buttons, menu items, links with visible text.",
    {
        "text": "text to find and click, e.g. 'Compose', 'Send', 'OK', 'Cancel'",
        "partial": "allow partial/fuzzy match (default true)",
    },
)(_ocr_click)

registry.register(
    "keyboard_navigate",
    "Execute a smart keyboard shortcut by name (address_bar, new_tab, copy, paste, back, find, etc.)",
    {"action": "shortcut action name, e.g. 'address_bar', 'new_tab', 'find', 'back', 'desktop'"},
)(_keyboard_navigate)

registry.register(
    "tab_click",
    "Press Tab N times then Enter — useful for keyboard-navigating forms and menus",
    {"tab_index": "how many times to press Tab before pressing Enter (default 1)"},
)(_tab_click)

registry.register(
    "type_paste",
    "Type text at the current cursor using clipboard paste — handles Unicode and long text reliably",
    {"text": "text to type/paste"},
)(_type_paste)

registry.register(
    "smart_click",
    "Click a UI element by description using OCR (no vision model needed). "
    "Finds visible text on screen and clicks it. Use this instead of visual_click for text elements.",
    {"description": "what to click, e.g. 'Compose', 'Sign in', 'Search bar', 'OK button'"},
)(_smart_click)
