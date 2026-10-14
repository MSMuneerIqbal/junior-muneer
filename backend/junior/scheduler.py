"""The built-in scheduler: checks every few minutes and runs what is due.

Phase 0 has one job: the daily backup. Later phases add scheduled posts and reminders.
"""

import asyncio
import logging
from collections.abc import Callable

from junior.backup import backup_if_due

log = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 5 * 60

# (name, job). A job runs in a worker thread and must decide itself whether it's due.
JOBS: list[tuple[str, Callable[[], object]]] = [("daily backup", backup_if_due)]


async def run_due_jobs() -> None:
    for name, job in JOBS:
        try:
            await asyncio.to_thread(job)
        except Exception:
            log.exception("Scheduled job %r failed; will try again next check", name)


async def scheduler_loop(interval: float = CHECK_EVERY_SECONDS) -> None:
    while True:
        await run_due_jobs()
        await asyncio.sleep(interval)
