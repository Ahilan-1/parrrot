"""
Parrrot — Self-learning tools.
Gives the agent the ability to research things it doesn't know,
save the knowledge to memory, and create reusable skill files.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

from parrrot.tools.registry import registry


async def _learn_about(topic: str, save_skill: bool = True) -> str:
    """
    When you don't know how to do something, call this.
    Opens Firefox, Googles the topic, reads pages with Tesseract OCR,
    extracts knowledge, saves to memory, and generates a skill file
    if the knowledge is a procedure.
    """
    from parrrot.core.learner import learn_about
    return await learn_about(topic, save_skill=save_skill)


def _create_skill(name: str, description: str, code: str) -> str:
    """
    Manually save a Python skill file to ~/.parrrot/skills/.
    The code must follow the Parrrot skill format:
      SKILL_NAME = "..."
      SKILL_DESCRIPTION = "..."
      SCHEDULE = None  # or cron string
      async def run(agent, memory, tools): ...
    """
    from parrrot.core.learner import save_skill_file
    try:
        path = save_skill_file(name, code)
        return f"Skill '{name}' saved to: {path}\nRestart daemon to activate it."
    except Exception as e:
        return f"Failed to save skill: {e}"


def _list_learned_skills() -> str:
    """List all auto-learned skills in ~/.parrrot/skills/."""
    from pathlib import Path
    skills_dir = Path.home() / ".parrrot" / "skills"
    if not skills_dir.exists():
        return "No skills directory found."
    files = sorted(skills_dir.glob("*.py"))
    if not files:
        return "No learned skills yet. Use learn_about to learn new things!"
    lines = [f"Learned skills ({len(files)}):"]
    for f in files:
        # Peek at SKILL_NAME
        try:
            text = f.read_text(encoding="utf-8")
            import re
            m = re.search(r'SKILL_NAME\s*=\s*["\'](.+?)["\']', text)
            d = re.search(r'SKILL_DESCRIPTION\s*=\s*["\'](.+?)["\']', text)
            name_str = m.group(1) if m else f.stem
            desc_str = d.group(1) if d else ""
            lines.append(f"  • {name_str}: {desc_str}")
        except Exception:
            lines.append(f"  • {f.name}")
    return "\n".join(lines)


def _reload_skills() -> str:
    """Reload all skills from ~/.parrrot/skills/ without restarting the daemon."""
    from parrrot.skills.loader import list_skills
    skills = list_skills()
    return f"Found {len(skills)} skill(s):\n" + "\n".join(
        f"  • {s['name']}: {s['description']}" for s in skills
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "learn_about",
    "Research a topic by opening Firefox, Googling it, reading pages with Tesseract OCR, "
    "extracting knowledge, saving to memory, and auto-generating a skill file if it's a procedure. "
    "Use this whenever you don't know how to do something.",
    {
        "topic": "what to learn, e.g. 'how to send a WhatsApp message' or 'Python asyncio'",
        "save_skill": "true to auto-generate a skill file from procedures (default true)",
    },
)(_learn_about)

registry.register(
    "create_skill",
    "Save a new Python skill file to ~/.parrrot/skills/",
    {
        "name": "skill name",
        "description": "what the skill does",
        "code": "full Python skill code",
    },
)(_create_skill)

registry.register(
    "list_learned_skills",
    "List all skills in ~/.parrrot/skills/",
    {},
)(_list_learned_skills)

registry.register(
    "reload_skills",
    "Reload all skill files without restarting",
    {},
)(_reload_skills)
