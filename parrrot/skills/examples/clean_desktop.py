"""
Parrrot Skill — Clean Desktop every Friday at 5pm
Part of the Parrrot open-source personal AI assistant.
"""

SKILL_NAME = "Clean Desktop"
SKILL_DESCRIPTION = "Every Friday at 5pm, organize the desktop by moving files into folders"
SCHEDULE = "0 17 * * 5"  # Every Friday 5:00pm


async def run(agent, memory, tools):
    result = await agent.run_task(
        "Please clean my desktop by organizing all files into subfolders by type. "
        "Tell me what you moved."
    )
    if memory:
        memory.remember("last_desktop_clean", result[:200])
