"""Persistent background-task progress, limits, status and cancellation."""
import time
from datetime import datetime
from statistics import median

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from junior.db import BackgroundTask, session_scope
from junior.db.models import utcnow

router = APIRouter()
STATUSES = ("running", "done", "failed", "cancelled")
MAX_RUNNING = 3


class TaskOut(BaseModel):
    id: int
    conversation_id: int | None
    title: str
    status: str
    message_id: int | None
    error: str
    cost_usd: float
    created_at: datetime
    finished_at: datetime | None
    worker: str
    output_format: str
    stage: str
    completed_steps: int
    total_steps: int
    started_at: datetime | None
    updated_at: datetime
    elapsed_seconds: int
    eta_seconds: int | None
    cost_limit_usd: float
    time_limit_seconds: int
    max_retries: int
    retries_used: int
    file_ids: list[int]


def _out(t: BackgroundTask, estimate: float | None = None) -> TaskOut:
    elapsed = int(max(0, ((t.finished_at or utcnow()) - (t.started_at or t.created_at)).total_seconds()))
    return TaskOut(
        id=t.id, conversation_id=t.conversation_id, title=t.title, status=t.status, message_id=t.message_id,
        error=t.error, cost_usd=t.cost_usd, created_at=t.created_at, finished_at=t.finished_at,
        worker=t.worker, output_format=t.output_format, stage=t.stage, completed_steps=t.completed_steps,
        total_steps=t.total_steps, started_at=t.started_at, updated_at=t.updated_at, elapsed_seconds=elapsed,
        eta_seconds=max(0, round(estimate - elapsed)) if estimate and t.status == "running" else None,
        cost_limit_usd=t.cost_limit_usd, time_limit_seconds=t.time_limit_seconds, max_retries=t.max_retries,
        retries_used=t.retries_used, file_ids=t.file_ids,
    )


def running_count() -> int:
    with session_scope() as s:
        return len(s.scalars(select(BackgroundTask.id).where(BackgroundTask.status == "running")).all())


def new_task(conversation_id: int | None, title: str, request: str, *, worker="junior_muneer", output_format="text",
             settings: dict | None = None) -> int:
    from junior.settings_store import all_settings
    settings = settings or all_settings()
    with session_scope() as s:
        task = BackgroundTask(conversation_id=conversation_id, title=title.strip()[:200] or "A task", request=request.strip(),
                              worker=worker, output_format=output_format, total_steps=5 if worker == "documents_agent" else 4,
                              cost_limit_usd=settings["task_budget_usd"], time_limit_seconds=settings["task_timeout_seconds"],
                              max_retries=settings["task_max_retries"])
        s.add(task)
        s.flush()
        return task.id


def finish_task(task_id: int, status: str, message_id: int | None = None, error: str = "", cost_usd: float = 0.0) -> None:
    with session_scope() as s:
        task = s.get(BackgroundTask, task_id)
        if task:
            task.status, task.message_id, task.error = status, message_id, error[:1000]
            task.cost_usd, task.finished_at, task.updated_at = cost_usd, utcnow(), utcnow()
            task.stage = "Finished" if status == "done" else "Cancelled" if status == "cancelled" else "Stopped"
            if status == "done":
                task.completed_steps = task.total_steps


def progress(task_id: int, stage: str, completed: int, context=None) -> None:
    with session_scope() as s:
        task = s.get(BackgroundTask, task_id)
        if task:
            if task.status == "running":
                task.started_at = task.started_at or utcnow()
                if stage:
                    task.stage = stage[:200]
                task.completed_steps = max(task.completed_steps, min(completed, task.total_steps))
            task.updated_at = utcnow()
            if context is not None:
                task.cost_usd = sum(u.cost_usd for u in context.usage)
                task.retries_used = context.task_retries_used
                task.file_ids = list(context.generated_file_ids)


class TaskStopped(RuntimeError):
    pass


def check_limits(context) -> None:
    from junior.costs import BudgetExceeded
    from junior.pause import is_paused
    from junior.permissions import get_mode
    if context.task_deadline is not None and time.monotonic() >= context.task_deadline:
        raise TaskStopped("The task time limit was reached.")
    if is_paused() or get_mode() == "plan":
        raise TaskStopped("Background work stopped because Pause or Plan mode was switched on.")
    with session_scope() as s:
        task = s.get(BackgroundTask, context.task_id)
        if task is None or task.status != "running":
            raise TaskStopped("This task was cancelled or is no longer running.")
        if task.conversation_id is None:
            raise TaskStopped("The originating chat was deleted, so the task stopped.")
    if context.task_budget_usd is not None and sum(u.cost_usd for u in context.usage) >= context.task_budget_usd:
        raise BudgetExceeded("The task cost allowance was reached; no further AI calls were made.")
    if context.task_model_calls >= 12:
        raise TaskStopped("The task reached its limit of 12 AI calls.")


def recover_interrupted() -> int:
    """Keep interrupted work visible; never replay external actions after a restart."""
    with session_scope() as s:
        stuck = s.scalars(select(BackgroundTask).where(BackgroundTask.status == "running")).all()
        for task in stuck:
            task.status, task.error, task.finished_at = "failed", "The app restarted before it finished. Ask again.", utcnow()
            task.stage, task.updated_at = "Interrupted by restart", utcnow()
        return len(stuck)


@router.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(conversation_id: int | None = None, status: str = "all", limit: int = 20) -> list[TaskOut]:
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, f"status must be 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(BackgroundTask).order_by(BackgroundTask.id.desc()).limit(max(1, min(limit, 100)))
        if conversation_id is not None:
            q = q.where(BackgroundTask.conversation_id == conversation_id)
        if status != "all":
            q = q.where(BackgroundTask.status == status)
        tasks = s.scalars(q).all()
        estimates = {}
        for t in tasks:
            key = (t.worker, t.output_format)
            if key not in estimates:
                history = s.scalars(select(BackgroundTask).where(
                    BackgroundTask.status == "done", BackgroundTask.worker == t.worker,
                    BackgroundTask.output_format == t.output_format, BackgroundTask.started_at.is_not(None)
                ).order_by(BackgroundTask.id.desc()).limit(10)).all()
                durations = [(r.finished_at - r.started_at).total_seconds() for r in history if r.finished_at]
                estimates[key] = median(durations) if durations else None
        return [_out(t, estimates[(t.worker, t.output_format)]) for t in tasks]


@router.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: int, request: Request) -> dict:
    # Match the dashboard's JSON requests; an unrelated website's HTML form must not cancel local work.
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "Use an application/json request to cancel a task.")
    with session_scope() as s:
        task = s.get(BackgroundTask, task_id)
        if task is None:
            raise HTTPException(404, "Task not found.")
        if task.status == "running":
            task.status, task.stage, task.updated_at = "cancelled", "Cancelling", utcnow()
        status = task.status
    return {"status": status}


def status_for(context, task_id: int = 0) -> str:
    if context.conversation_id is None:
        return "No task in this chat yet."
    tasks = list_tasks(context.conversation_id, "all", 20)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
    if not tasks:
        return "No matching task in this chat."
    lines = []
    for t in tasks:
        eta = f"about {t.eta_seconds}s left, based on similar finished tasks" if t.eta_seconds else "no reliable time estimate yet"
        files = " ".join(f"[Download](/api/files/{i}/download)" for i in t.file_ids)
        lines.append(f"Task {t.id}: {t.title} — {t.status}; {t.stage}; {t.completed_steps}/{t.total_steps} steps; "
                     f"{t.elapsed_seconds}s elapsed; {eta}; ${t.cost_usd:.4f} of ${t.cost_limit_usd:.2f} allowance. {files} {t.error}")
    return "\n".join(lines)
