"""Audit log: every agent run, tool call, web search, memory change and setting change.

    GET /api/activity?kind=&limit=&before_id=   newest first; before_id pages back
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from junior.db import AuditLog, session_scope

log = logging.getLogger("junior.audit")
router = APIRouter()

KINDS = ("agent_run", "tool_call", "web_search", "memory", "setting", "system")
MAX_TEXT = 500


def _short(value: Any) -> Any:
    """Keep log rows small: long text is cut."""
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + f"… (+{len(value) - MAX_TEXT} chars)"
    if isinstance(value, dict):
        return {k: _short(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_short(v) for v in value]
    return value


def audit(
    kind: str,
    name: str,
    *,
    result: str = "ok",
    detail: dict[str, Any] | None = None,
    cost_usd: float = 0.0,
    conversation_id: int | None = None,
) -> None:
    """Write one audit row. Never raises: logging must not break the work."""
    assert kind in KINDS, kind
    try:
        with session_scope() as s:
            s.add(
                AuditLog(
                    kind=kind,
                    name=name,
                    result=result,
                    detail=_short(detail or {}),
                    cost_usd=cost_usd,
                    conversation_id=conversation_id,
                )
            )
        log.info("%s %s -> %s ($%.5f)", kind, name, result, cost_usd)
    except Exception:
        log.exception("Could not write audit row %s %s", kind, name)


class ActivityOut(BaseModel):
    id: int
    created_at: datetime
    kind: str
    name: str
    result: str
    detail: dict[str, Any]
    cost_usd: float
    conversation_id: int | None


@router.get("/api/activity", response_model=list[ActivityOut])
def activity(kind: str = "", limit: int = 100, before_id: int | None = None) -> list[ActivityOut]:
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))
    if kind:
        query = query.where(AuditLog.kind.in_(kind.split(",")))
    if before_id:
        query = query.where(AuditLog.id < before_id)
    with session_scope() as s:
        return [
            ActivityOut(
                id=r.id,
                created_at=r.created_at,
                kind=r.kind,
                name=r.name,
                result=r.result,
                detail=r.detail,
                cost_usd=r.cost_usd,
                conversation_id=r.conversation_id,
            )
            for r in s.scalars(query)
        ]


@router.get("/api/activity/kinds")
def activity_kinds() -> list[str]:
    return list(KINDS)
