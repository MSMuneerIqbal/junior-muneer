"""Long tasks in the background (P7-02).

Junior Muneer says "I'm on it", you keep chatting, and the finished result is posted to the
same chat as a new answer (with any draft cards). The work is a normal Junior Muneer turn, so
the same agents, approvals, permissions, pause and daily cost cap apply.

    GET /api/tasks?conversation_id=&status=running|done|failed|all
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from junior.db import BackgroundTask, session_scope
from junior.db.models import utcnow

router = APIRouter()
STATUSES = ("running", "done", "failed")
MAX_RUNNING = 3  # at a time, so a loop can't start dozens


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


def _out(t: BackgroundTask) -> TaskOut:
    return TaskOut(
        id=t.id, conversation_id=t.conversation_id, title=t.title, status=t.status, message_id=t.message_id,
        error=t.error, cost_usd=t.cost_usd, created_at=t.created_at, finished_at=t.finished_at,
    )


def running_count() -> int:
    with session_scope() as s:
        return len(s.scalars(select(BackgroundTask.id).where(BackgroundTask.status == "running")).all())


def new_task(conversation_id: int, title: str, request: str) -> int:
    with session_scope() as s:
        task = BackgroundTask(conversation_id=conversation_id, title=title.strip()[:200] or "A task", request=request.strip())
        s.add(task)
        s.flush()
        return task.id


def finish_task(task_id: int, status: str, message_id: int | None = None, error: str = "", cost_usd: float = 0.0) -> None:
    with session_scope() as s:
        task = s.get(BackgroundTask, task_id)
        if task:
            task.status, task.message_id, task.error = status, message_id, error[:1000]
            task.cost_usd, task.finished_at = cost_usd, utcnow()


def recover_interrupted() -> int:
    """At startup: tasks still 'running' were stopped by a restart."""
    with session_scope() as s:
        stuck = s.scalars(select(BackgroundTask).where(BackgroundTask.status == "running")).all()
        for task in stuck:
            task.status, task.error, task.finished_at = "failed", "The app restarted before it finished. Ask again.", utcnow()
        return len(stuck)


@router.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(conversation_id: int | None = None, status: str = "all", limit: int = 20) -> list[TaskOut]:
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, f"status must be 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(BackgroundTask).order_by(BackgroundTask.id.desc()).limit(min(limit, 100))
        if conversation_id is not None:
            q = q.where(BackgroundTask.conversation_id == conversation_id)
        if status != "all":
            q = q.where(BackgroundTask.status == status)
        return [_out(t) for t in s.scalars(q)]
