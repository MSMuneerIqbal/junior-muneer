"""The built-in scheduler: checks every few minutes and runs what is due.

Jobs: the daily backup, and reminders for planned posts (P2-11).
"""

import asyncio
import logging
from collections.abc import Callable

from junior.approvals import remind_due
from junior.backup import backup_if_due

log = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 60  # often enough for post reminders; each job is cheap when nothing is due

# (name, job). A job runs in a worker thread and must decide itself whether it's due.
JOBS: list[tuple[str, Callable[[], object]]] = [
    ("daily backup", backup_if_due),
    ("post reminders", remind_due),
]


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
