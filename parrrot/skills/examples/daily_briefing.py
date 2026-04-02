"""
Parrrot Skill — Morning Briefing every day at 8am
Part of the Parrrot open-source personal AI assistant.
"""

SKILL_NAME = "Morning Briefing"
SKILL_DESCRIPTION = "Every morning at 8am, summarize emails and calendar events"
SCHEDULE = "0 8 * * *"  # Every day at 8:00am


async def run(agent, memory, tools):
    result = await agent.run_task(
        "Good morning briefing: check my unread emails, today's calendar events, "
        "and give me a short summary of what I need to know today. "
        "Then send me a desktop notification with the highlights."
    )
    if memory:
        memory.remember("last_briefing_summary", result[:300])
