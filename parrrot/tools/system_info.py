"""
Parrrot — System information tools
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import platform

import psutil
from datetime import datetime, timezone

from parrrot.tools.registry import registry


def _get_system_info() -> str:
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    battery = psutil.sensors_battery()

    lines = [
        f"OS:      {platform.system()} {platform.release()} ({platform.machine()})",
        f"CPU:     {cpu:.1f}% used  |  {psutil.cpu_count()} cores",
        f"RAM:     {mem.percent:.1f}% used  ({mem.used // 1024**2:,} MB / {mem.total // 1024**2:,} MB)",
        f"Disk:    {disk.percent:.1f}% used  ({disk.free // 1024**3:.1f} GB free)",
    ]
    if battery:
        charging = "charging" if battery.power_plugged else "on battery"
        lines.append(f"Battery: {battery.percent:.0f}%  ({charging})")
    return "\n".join(lines)


def _get_battery() -> str:
    battery = psutil.sensors_battery()
    if not battery:
        return "No battery detected (desktop or battery info unavailable)"
    status = "charging" if battery.power_plugged else "discharging"
    secs = battery.secsleft
    if secs == psutil.POWER_TIME_UNLIMITED:
        time_str = "unlimited (plugged in)"
    elif secs == psutil.POWER_TIME_UNKNOWN:
        time_str = "unknown"
    else:
        h, m = divmod(secs // 60, 60)
        time_str = f"{h}h {m}m remaining"
    return f"Battery: {battery.percent:.0f}%  {status}  —  {time_str}"


def _get_disk_usage(path: str = "/") -> str:
    try:
        usage = psutil.disk_usage(path)
        return (
            f"Disk usage for {path}:\n"
            f"  Total:  {usage.total // 1024**3:.1f} GB\n"
            f"  Used:   {usage.used // 1024**3:.1f} GB ({usage.percent:.1f}%)\n"
            f"  Free:   {usage.free // 1024**3:.1f} GB"
        )
    except Exception as e:
        return f"Error: {e}"


def _get_date() -> str:
    """Return the current date/time in ISO format (local time + UTC)."""
    now_local = datetime.now().astimezone()
    now_utc = datetime.now(timezone.utc)
    return f"Local: {now_local.isoformat()} | UTC: {now_utc.isoformat()}"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "get_system_info",
    "Get CPU, RAM, disk, and battery info",
    {},
)(_get_system_info)

registry.register(
    "get_battery",
    "Get battery percentage and charging status",
    {},
)(_get_battery)

registry.register(
    "get_disk_usage",
    "Get disk usage for a path",
    {"path": "disk path (default '/')"},
)(_get_disk_usage)

registry.register(
    "get_date",
    "Get the current date/time in ISO format (local + UTC).",
    {},
)(_get_date)
