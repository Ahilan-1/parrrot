"""
Parrrot — Desktop notifications with multi-layer fallbacks.
Windows: PowerShell balloon tip (no extra deps) → plyer → win10toast
macOS:   osascript (built-in)
Linux:   notify-send (built-in)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import platform
import subprocess
import sys
from typing import Optional

from parrrot.tools.registry import registry

_SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Platform-specific senders
# ---------------------------------------------------------------------------

def _notify_windows(title: str, message: str, timeout: int = 10) -> bool:
    """Windows balloon tip via PowerShell — zero extra dependencies."""
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$global:notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipIcon  = [System.Windows.Forms.ToolTipIcon]::Info
$notify.BalloonTipTitle = '{title.replace("'", "''")}'
$notify.BalloonTipText  = '{message.replace("'", "''")}'
$notify.Visible = $true
$notify.ShowBalloonTip({timeout * 1000})
Start-Sleep -Milliseconds {min(timeout * 1000, 5000)}
$notify.Dispose()
"""
    try:
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=timeout + 5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _notify_windows_toast(title: str, message: str, timeout: int = 10) -> bool:
    """Windows 10/11 toast via win10toast library (optional)."""
    try:
        from win10toast import ToastNotifier  # type: ignore[import]
        t = ToastNotifier()
        t.show_toast(title, message, duration=timeout, threaded=True)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def _notify_windows_msgbox(title: str, message: str) -> bool:
    """Last-resort: PowerShell message box — always works on Windows."""
    try:
        subprocess.Popen(
            [
                "powershell", "-WindowStyle", "Hidden", "-Command",
                f"[System.Windows.Forms.MessageBox]::Show("
                f"'{message.replace(chr(39), chr(39)*2)}',"
                f"'{title.replace(chr(39), chr(39)*2)}',"
                f"[System.Windows.Forms.MessageBoxButtons]::OK,"
                f"[System.Windows.Forms.MessageBoxIcon]::Information)"
                f" | Out-Null",
            ]
        )
        return True
    except Exception:
        return False


def _notify_plyer(title: str, message: str, timeout: int = 10) -> bool:
    try:
        from plyer import notification as plyer_notif
        plyer_notif.notify(title=title, message=message, app_name="Parrrot", timeout=timeout)
        return True
    except Exception:
        return False


def _notify_macos(title: str, message: str) -> bool:
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def _notify_linux(title: str, message: str, timeout: int = 10) -> bool:
    try:
        subprocess.run(
            ["notify-send", "-t", str(timeout * 1000), title, message],
            capture_output=True, timeout=5,
        )
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public sender — tries methods in order until one works
# ---------------------------------------------------------------------------

def send_notification(title: str, message: str, timeout: int = 10) -> str:
    """
    Send a desktop notification using the best available method for the OS.
    Always returns a status string.
    """
    title = str(title)
    message = str(message)

    if _SYSTEM == "Windows":
        if _notify_windows(title, message, timeout):
            return f"Notification sent: '{title}'"
        if _notify_windows_toast(title, message, timeout):
            return f"Notification sent (win10toast): '{title}'"
        if _notify_plyer(title, message, timeout):
            return f"Notification sent (plyer): '{title}'"
        # Last resort — popup box
        _notify_windows_msgbox(title, message)
        return f"Notification shown as popup: '{title}'"

    elif _SYSTEM == "Darwin":
        if _notify_macos(title, message):
            return f"Notification sent: '{title}'"
        if _notify_plyer(title, message, timeout):
            return f"Notification sent (plyer): '{title}'"
        return f"Notification failed on macOS. Try: pip install plyer"

    else:  # Linux
        if _notify_linux(title, message, timeout):
            return f"Notification sent: '{title}'"
        if _notify_plyer(title, message, timeout):
            return f"Notification sent (plyer): '{title}'"
        return f"Notification failed. Install notify-send: sudo apt install libnotify-bin"


def _send_notification_tool(title: str, message: str, timeout: int = 10) -> str:
    return send_notification(title, message, timeout)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "send_notification",
    "Send a desktop notification (Windows balloon tip / macOS banner / Linux notify-send)",
    {
        "title": "notification title",
        "message": "notification body text",
        "timeout": "seconds to show (default 10)",
    },
)(_send_notification_tool)
