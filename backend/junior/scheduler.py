"""The built-in scheduler: checks every few minutes and runs what is due.

Jobs: the daily backup, reminders for planned posts (P2-11) and Fiverr orders (P5-08), and the morning news digests
(Phase 2b, added by the app because it needs the agents).
"""

import asyncio
import inspect
import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from junior.approvals import remind_due
from junior.audit import audit
from junior.backup import backup_if_due
from junior.config import get_settings
from junior.freelance.orders import remind_orders
from junior.settings_store import all_settings, get_setting, set_setting

log = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 60  # often enough for post reminders; each job is cheap when nothing is due

router = APIRouter()

# Existing switches are shared with News & email; these IDs cannot select arbitrary code.
CATALOG = {
    "news": ("Morning news digests", "Daily at {news_digest_time} ({timezone})", "news_digest_enabled"),
    "news_email": ("Daily AI news email", "After the day's digest is ready", "news_email_enabled"),
    "briefing": ("Morning briefing", "Daily at {briefing_time} ({timezone})", "briefing_enabled"),
    "inbox": ("Gmail inbox watcher", "Checks approximately every five minutes", "email_watch_enabled"),
    "memory": ("Memory tidy-up", "Weekly when enough memories are available", "memory_tidy_enabled"),
    "feeds": ("Your feeds", "Checks approximately every three hours", "scheduled_feeds_enabled"),
    "backup": ("Daily backup", "Once daily", "scheduled_backup_enabled"),
    "posts": ("Planned post reminders", "Checks every minute for due reminders", "scheduled_posts_enabled"),
    "orders": ("Fiverr order reminders", "Checks every minute for due reminders", "scheduled_orders_enabled"),
}
JOB_SWITCHES = {"daily backup": "scheduled_backup_enabled", "post reminders": "scheduled_posts_enabled",
                "order reminders": "scheduled_orders_enabled", "your feeds": "scheduled_feeds_enabled"}


class ScheduledJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.get("/api/scheduled-jobs")
def scheduled_jobs() -> dict:
    settings = all_settings()
    return {"scheduler_running": get_settings().scheduler_enabled,
            "paused": settings["paused"],
            "jobs": [{"id": key, "title": title, "schedule": schedule.format(**settings), "enabled": settings[setting]}
                     for key, (title, schedule, setting) in CATALOG.items()]}


@router.patch("/api/scheduled-jobs/{job_id}")
def update_scheduled_job(job_id: str, body: ScheduledJobUpdate) -> dict:
    job = CATALOG.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    setting = job[2]
    before = get_setting(setting)
    if before != body.enabled:
        set_setting(setting, body.enabled)
        audit("setting", setting, detail={"before": before, "after": body.enabled})
    return scheduled_jobs()

# (name, job). A plain job runs in a worker thread, an async one on the event loop; each
# must decide itself whether it's due.
JOBS: list[tuple[str, Callable[[], object]]] = [
    ("daily backup", backup_if_due),
    ("post reminders", remind_due),
    ("order reminders", remind_orders),
]


async def run_due_jobs(extra: list[tuple[str, Callable[[], object]]] | None = None) -> None:
    for name, job in [*JOBS, *(extra or [])]:
        try:
            if name in JOB_SWITCHES and not get_setting(JOB_SWITCHES[name]):
                continue
            if inspect.iscoroutinefunction(job):
                await job()
            else:
                await asyncio.to_thread(job)
        except Exception:
            log.exception("Scheduled job %r failed; will try again next check", name)


async def scheduler_loop(
    interval: float = CHECK_EVERY_SECONDS, extra: list[tuple[str, Callable[[], object]]] | None = None
) -> None:
    while True:
        await run_due_jobs(extra)
        await asyncio.sleep(interval)
