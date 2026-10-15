"""Content ideas from the Social Media Manager.

    GET  /api/ideas?status=new|used|dismissed|all
    POST /api/ideas/{id}/dismiss
    POST /api/ideas/{id}/restore
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from junior.db import Idea, session_scope

router = APIRouter()

STATUSES = ("new", "used", "dismissed")
KINDS = ("project", "lesson", "how_to", "milestone", "opinion", "other")
MAX_OPEN = 50


class IdeaOut(BaseModel):
    id: int
    platform: str
    title: str
    angle: str
    kind: str
    status: str
    approval_id: int | None
    created_at: datetime


def _out(i: Idea) -> IdeaOut:
    return IdeaOut(
        id=i.id, platform=i.platform, title=i.title, angle=i.angle, kind=i.kind,
        status=i.status, approval_id=i.approval_id, created_at=i.created_at,
    )


def add_ideas(items: list[dict]) -> list[IdeaOut]:
    with session_scope() as s:
        rows = [
            Idea(
                platform=i["platform"],
                title=i["title"].strip()[:200],
                angle=i.get("angle", "").strip(),
                kind=i.get("kind") if i.get("kind") in KINDS else "other",
            )
            for i in items
            if i.get("title", "").strip()
        ]
        s.add_all(rows)
        s.flush()
        return [_out(r) for r in rows]


def open_ideas(limit: int = 20) -> list[IdeaOut]:
    with session_scope() as s:
        q = select(Idea).where(Idea.status == "new").order_by(Idea.id.desc()).limit(limit)
        return [_out(i) for i in s.scalars(q)]


def get_idea(idea_id: int) -> IdeaOut | None:
    with session_scope() as s:
        i = s.get(Idea, idea_id)
        return _out(i) if i else None


def mark_used(idea_id: int, approval_id: int | None) -> None:
    with session_scope() as s:
        i = s.get(Idea, idea_id)
        if i:
            i.status = "used"
            i.approval_id = approval_id


def _set_status(idea_id: int, status: str) -> IdeaOut:
    with session_scope() as s:
        i = s.get(Idea, idea_id)
        if i is None:
            raise HTTPException(404, f"Idea {idea_id} doesn't exist.")
        i.status = status
        s.flush()
        return _out(i)


@router.get("/api/ideas", response_model=list[IdeaOut])
def list_ideas(status: str = "new", limit: int = 100) -> list[IdeaOut]:
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, f"status must be 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(Idea).order_by(Idea.id.desc()).limit(min(limit, 500))
        if status != "all":
            q = q.where(Idea.status == status)
        return [_out(i) for i in s.scalars(q)]


@router.post("/api/ideas/{idea_id}/dismiss", response_model=IdeaOut)
def dismiss(idea_id: int) -> IdeaOut:
    return _set_status(idea_id, "dismissed")


@router.post("/api/ideas/{idea_id}/restore", response_model=IdeaOut)
def restore(idea_id: int) -> IdeaOut:
    return _set_status(idea_id, "new")
