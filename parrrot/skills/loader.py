"""
Parrrot — Skill auto-loader
Scans ~/.parrrot/skills/ for .py files and loads them as scheduled tasks.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parrrot.core.scheduler import Scheduler

logger = logging.getLogger("parrrot.skills")

SKILLS_DIR = Path.home() / ".parrrot" / "skills"

# Required attributes for a skill module
REQUIRED_ATTRS = ("SKILL_NAME", "SKILL_DESCRIPTION", "run")


def _load_skill_module(path: Path):
    """Dynamically load a skill .py file as a module."""
    spec = importlib.util.spec_from_file_location(f"parrrot_skill_{path.stem}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        return module
    except Exception as e:
        logger.warning(f"Failed to load skill {path.name}: {e}")
        return None


def load_all_skills(scheduler: "Scheduler", agent) -> list[dict]:
    """
    Scan SKILLS_DIR for .py files, load them, and register any
    that have a SCHEDULE attribute with the scheduler.

    Returns list of loaded skill metadata dicts.
    """
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    loaded: list[dict] = []

    for skill_file in sorted(SKILLS_DIR.glob("*.py")):
        if skill_file.name.startswith("_"):
            continue

        module = _load_skill_module(skill_file)
        if module is None:
            continue

        # Validate required attributes
        missing = [a for a in REQUIRED_ATTRS if not hasattr(module, a)]
        if missing:
            logger.warning(f"Skill {skill_file.name} missing: {missing}")
            continue

        name = getattr(module, "SKILL_NAME", skill_file.stem)
        description = getattr(module, "SKILL_DESCRIPTION", "")
        schedule = getattr(module, "SCHEDULE", None)

        if schedule and scheduler:
            async def _make_job(m=module, a=agent):
                try:
                    await m.run(agent=a, memory=None, tools=None)
                except Exception as exc:
                    logger.error(f"Skill '{m.SKILL_NAME}' failed: {exc}")

            try:
                scheduler.add_cron_job(
                    _make_job,
                    cron_expr=schedule,
                    job_id=f"skill_{skill_file.stem}",
                    name=name,
                )
                logger.info(f"Loaded skill: {name} (cron: {schedule})")
            except Exception as e:
                logger.warning(f"Could not schedule skill {name}: {e}")

        loaded.append({"name": name, "description": description, "schedule": schedule, "file": str(skill_file)})

    return loaded


def list_skills() -> list[dict]:
    """List all skills in the skills directory without loading them."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills: list[dict] = []
    for f in sorted(SKILLS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module = _load_skill_module(f)
        if module:
            skills.append({
                "name": getattr(module, "SKILL_NAME", f.stem),
                "description": getattr(module, "SKILL_DESCRIPTION", ""),
                "schedule": getattr(module, "SCHEDULE", None),
                "file": str(f),
            })
    return skills
