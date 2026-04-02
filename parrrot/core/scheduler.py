"""
Parrrot — APScheduler-based background task scheduler
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

from parrrot import config as cfg

logger = logging.getLogger("parrrot.scheduler")


def _get_scheduler():
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        return AsyncIOScheduler
    except ImportError:
        return None


class Scheduler:
    """Wraps APScheduler to manage Parrrot's background tasks."""

    def __init__(self) -> None:
        AsyncIOScheduler = _get_scheduler()
        if AsyncIOScheduler is None:
            raise ImportError(
                "APScheduler not installed. Install with: pip install apscheduler"
            )
        self._sched = AsyncIOScheduler(timezone="UTC")
        self._agent = None  # Set when daemon starts

    def set_agent(self, agent) -> None:
        self._agent = agent

    def add_cron_job(
        self,
        func: Callable,
        cron_expr: str,
        job_id: str,
        name: str = "",
    ) -> None:
        """Add a job using a cron expression like '0 8 * * *'."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        minute, hour, day, month, day_of_week = parts
        self._sched.add_job(
            func,
            trigger="cron",
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            id=job_id,
            name=name or job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled job '{job_id}' ({cron_expr})")

    def add_interval_job(
        self,
        func: Callable,
        seconds: int,
        job_id: str,
        name: str = "",
    ) -> None:
        """Add a recurring interval job."""
        self._sched.add_job(
            func,
            trigger="interval",
            seconds=seconds,
            id=job_id,
            name=name or job_id,
            replace_existing=True,
        )

    def start(self) -> None:
        conf = cfg.load()
        if not conf["scheduler"].get("enabled", True):
            logger.info("Scheduler disabled in config.")
            return

        # Built-in heartbeat
        heartbeat_interval = conf["scheduler"].get("heartbeat_interval", 300)
        self.add_interval_job(
            self._heartbeat,
            seconds=heartbeat_interval,
            job_id="parrrot_heartbeat",
            name="Heartbeat",
        )

        self._sched.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    async def _heartbeat(self) -> None:
        """
        Called every N minutes. Check for anything the agent should proactively do.
        """
        if self._agent is None:
            return
        try:
            result = await self._agent.think_and_act(
                "Heartbeat check: review your scheduled tasks and memory. "
                "Is there anything you should proactively do right now? "
                "If nothing is needed, just say 'All good.' and nothing else."
            )
            if result and "all good" not in result.lower():
                # Something needs attention — send notification
                try:
                    from parrrot.tools.notifications import _send_notification
                    _send_notification("Parrrot", result[:200])
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")

    def list_jobs(self) -> list[dict]:
        jobs = []
        for job in self._sched.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(next_run) if next_run else "N/A",
            })
        return jobs
