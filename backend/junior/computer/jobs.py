"""P11-01: bounded local command jobs. The live manager owns handles; SQLite owns history.

No stored PID is ever used to stop/resume a process. No automatic retries. Start only through approved dispatch.
"""

import asyncio
import codecs
import re
import time
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select

from junior.audit import audit
from junior.computer import owned_process
from junior.computer.paths import recheck
from junior.computer.terminal import refusal
from junior.db import ApprovalItem, ComputerJob, session_scope
from junior.db.models import utcnow
from junior.pause import is_paused
from junior.permissions import get_mode
from junior.senders.base import Outgoing
from junior.senders.guard import NEVER_SEND, check as check_approval
from junior.settings_store import get_setting

MAX_SECONDS = 3600
DEFAULT_SECONDS = 600
MAX_RUNNING = 3
OUTPUT_CHARS = 16000
ACTIVE = ("starting", "running")


class JobError(ValueError):
    pass


def validate_seconds(seconds: int) -> int:
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= MAX_SECONDS:
        raise JobError(f"Choose a whole-number time limit between 1 and {MAX_SECONDS} seconds.")
    return seconds


def redact(text: str) -> str:
    for pattern, _ in NEVER_SEND:
        text = pattern.sub("[secret redacted]", text)
    text = re.sub(r"\bAIza[\w-]{25,}", "[secret redacted]", text)
    return re.sub(r"(?i)\b([\w]*(?:api[_-]?key|token|secret|password)[\w]*\s*[:=]\s*)\S+",
                  r"\1[redacted]", text)


def as_dict(row: ComputerJob) -> dict:
    return {key: getattr(row, key) for key in (
        "id", "approval_id", "conversation_id", "command", "folder", "seconds", "state", "output",
        "output_chars", "exit_code", "note", "created_at", "started_at", "finished_at",
    )} | {"output_truncated": row.output_chars > OUTPUT_CHARS}


def list_jobs(limit: int = 50) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(select(ComputerJob).order_by(
            ComputerJob.state.in_(ACTIVE).desc(), ComputerJob.created_at.desc()
        ).limit(limit)).all()
        return [as_dict(row) for row in rows]


def get_job(job_id: str) -> dict:
    with session_scope() as s:
        row = s.get(ComputerJob, job_id)
        if row is None:
            raise LookupError("That PC job doesn't exist.")
        return as_dict(row)


def recover_interrupted() -> int:
    """A crash may have interrupted the command. Never replay it or kill an old/reused PID."""
    with session_scope() as s:
        rows = s.scalars(select(ComputerJob).where(ComputerJob.state.in_(ACTIVE))).all()
        for row in rows:
            row.state, row.finished_at = "interrupted", utcnow()
            row.note = "The backend stopped during this job. Check any partial changes before starting another job."
            row.pid = None
        return len(rows)


@dataclass
class LiveJob:
    proc: asyncio.subprocess.Process
    tree: owned_process.OwnedTree
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str = "Stopped by you. Partial changes may remain."
    task: asyncio.Task | None = None


class JobManager:
    def __init__(self):
        self.live: dict[str, LiveJob] = {}
        self.lock = asyncio.Lock()
        self.closing = False

    async def start(self, out: Outgoing) -> str:
        async with self.lock:
            if self.closing:
                raise JobError("The backend is shutting down; nothing started.")
            with session_scope() as s:
                item = s.get(ApprovalItem, out.item_id)
                if (item is None or out.action_type != "computer.run" or item.action_type != "computer.run"
                        or item.meta.get("op") != "start_job" or out.meta.get("op") != "start_job"
                        or any(out.meta.get(k) != item.meta.get(k) for k in ("path", "seconds"))):
                    raise JobError("This isn't the approved background command; nothing started.")
                if problems := check_approval(item, out.text):
                    raise JobError(problems[0])
                if s.scalar(select(ComputerJob.id).where(ComputerJob.approval_id == out.item_id)):
                    raise JobError("This card already started a job. Check its status; it will not run twice.")
                conversation_id = item.conversation_id
            if len(self.live) >= MAX_RUNNING:
                raise JobError(f"At most {MAX_RUNNING} PC jobs can run together. Stop one or wait for it to finish.")
            if get_mode() == "plan":
                raise JobError("Plan mode is on; nothing started.")
            folder = recheck(out.meta.get("path", ""))
            if not folder.is_dir():
                raise JobError("The approved folder no longer exists; nothing started.")
            seconds = validate_seconds(out.meta.get("seconds", DEFAULT_SECONDS))
            if why := refusal(out.text):
                raise JobError(f"That command is never run here ({why}).")
            job_id = str(uuid4())
            with session_scope() as s:
                s.add(ComputerJob(id=job_id, approval_id=out.item_id, conversation_id=conversation_id,
                                  command=out.text, folder=str(folder), seconds=seconds, state="starting"))
            try:
                proc, tree = await owned_process.spawn(out.text, str(folder))
            except BaseException:
                with session_scope() as s:
                    row = s.get(ComputerJob, job_id)
                    row.state, row.finished_at = "failed", utcnow()
                    row.note = "Couldn't start the supervised process. No automatic retry."
                raise
            live = LiveJob(proc, tree)
            try:
                with session_scope() as s:
                    row = s.get(ComputerJob, job_id)
                    row.state, row.started_at, row.pid = "running", utcnow(), proc.pid
            except BaseException:
                tree.close()
                await proc.communicate()
                raise
            self.live[job_id] = live
            live.task = asyncio.create_task(self._watch(job_id, live, seconds), name=f"pc-job-{job_id}")
            audit("action", "computer.job.started", detail={"job_id": job_id, "seconds": seconds},
                  conversation_id=conversation_id)
            return job_id

    async def _watch(self, job_id: str, live: LiveJob, seconds: int):
        raw, total, flushed, saved_total = "", 0, time.monotonic(), 0

        def save_output():
            nonlocal saved_total
            if saved_total == total:
                return
            with session_scope() as s:
                row = s.get(ComputerJob, job_id)
                row.output, row.output_chars = redact(raw)[-OUTPUT_CHARS:], total
            saved_total = total

        async def read_output():
            nonlocal raw, total, flushed
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while data := await live.proc.stdout.read(4096):
                text = decoder.decode(data)
                raw, total = (raw + text)[-OUTPUT_CHARS:], total + len(text)
                if time.monotonic() - flushed >= 0.25:
                    save_output()
                    flushed = time.monotonic()
            text = decoder.decode(b"", final=True)
            raw, total = (raw + text)[-OUTPUT_CHARS:], total + len(text)
            save_output()

        reader = asyncio.create_task(read_output())
        state, note = "completed", "Finished (exit code 0)."
        deadline = time.monotonic() + seconds
        try:
            while live.proc.returncode is None:
                if reader.done() and not reader.cancelled() and reader.exception():
                    raise JobError("Output capture failed.")
                if total and time.monotonic() - flushed >= 0.25:
                    save_output()
                    flushed = time.monotonic()
                if live.stop.is_set():
                    state, note = "stopped", live.reason
                    break
                if is_paused() or not get_setting("computer_enabled") or get_mode() == "plan":
                    state, note = "stopped", "Stopped because Junior was paused, Computer tools were turned off, or Plan mode was enabled."
                    break
                if time.monotonic() >= deadline:
                    state, note = "timed_out", f"Stopped after {seconds} seconds (the time limit). Partial changes may remain."
                    break
                await asyncio.sleep(0.2)
            live.tree.close()  # also stops any child that outlived the root shell and still holds its stdout
            await live.proc.wait()
            await reader
            if state == "completed" and live.proc.returncode != 0:
                state, note = "failed", f"Finished with an error (exit code {live.proc.returncode})."
        except asyncio.CancelledError:
            state, note = "interrupted", "The backend stopped during the job. Check any partial changes."
        except Exception:
            state, note = "interrupted", "Job supervision failed. The owned process tree was stopped; check partial changes."
        finally:
            live.tree.close()
            await live.proc.wait()
            await asyncio.gather(reader, return_exceptions=True)
            # Consume errors from the reader, too; do not leave an unobserved background exception.
            if reader.done() and not reader.cancelled() and reader.exception():
                state, note = "interrupted", "Couldn't capture job output. Check any partial changes."
            with session_scope() as s:
                row = s.get(ComputerJob, job_id)
                row.state, row.note, row.finished_at = state, note, utcnow()
                row.exit_code, row.pid = live.proc.returncode, None
            self.live.pop(job_id, None)
            audit("action", "computer.job.finished", result="ok" if state == "completed" else "error",
                  detail={"job_id": job_id, "state": state})

    async def stop(self, job_id: str, reason: str = "Stopped by you. Partial changes may remain.") -> dict:
        row = get_job(job_id)
        if row["state"] not in ACTIVE:
            return row
        live = self.live.get(job_id)
        if live is None:
            raise JobError("This process isn't owned by this backend. Restart recovery must resolve it; no PID was killed.")
        live.reason = reason
        live.stop.set()
        await asyncio.shield(live.task)
        return get_job(job_id)

    async def close(self):
        async with self.lock:
            self.closing = True
            active = list(self.live.values())
            for live in active:
                live.reason = "Stopped because the backend shut down. Not automatically restarted."
                live.stop.set()
        await asyncio.gather(*(live.task for live in active), return_exceptions=True)
