"""
Parrrot Skill — Watch Desktop for new files and report
Part of the Parrrot open-source personal AI assistant.
"""

SKILL_NAME = "Desktop Watcher"
SKILL_DESCRIPTION = "Every 10 minutes, check if any new files appeared on the desktop"
SCHEDULE = "*/10 * * * *"  # Every 10 minutes

import platform
import os
from pathlib import Path

_last_seen: set[str] = set()


def _desktop() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    return Path.home() / "Desktop"


async def run(agent, memory, tools):
    global _last_seen
    desktop = _desktop()
    if not desktop.exists():
        return

    current = {item.name for item in desktop.iterdir()}
    new_files = current - _last_seen

    if _last_seen and new_files:
        files_str = ", ".join(sorted(new_files))
        await agent.run_task(
            f"New files appeared on the desktop: {files_str}. "
            f"Send a desktop notification telling the user."
        )

    _last_seen = current
