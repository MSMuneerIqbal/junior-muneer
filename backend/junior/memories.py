"""Long-term memories about you: storage helpers and the REST API.

    GET    /api/memories         list (newest first)
    POST   /api/memories         add one yourself
    PATCH  /api/memories/{id}    edit
    DELETE /api/memories/{id}    delete (also the "undo" on a "Memory updated" note)
    GET    /api/memories/archived         the ones the tidy-up archived, with why
    POST   /api/memories/{id}/restore     bring one back
    POST   /api/memories/tidy             tidy up now
"""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.audit import audit
from junior.db import Memory, session_scope
from junior.timeutil import zone

# How many memories go into Junior Muneer's instructions each turn. With more, he gets the
# newest ones plus the older ones that fit your message, and can search the rest (recall_memory).
MAX_IN_PROMPT = 100
NEWEST_IN_PROMPT = 60
_WORD = re.compile(r"[^\W_]{3,}")
_COMMON = {"the", "and", "for", "you", "your", "with", "that", "this", "are", "was", "have", "has", "from", "about",
           "what", "when", "how", "who", "his", "her", "they", "them", "but", "not", "can", "will", "hai", "hain", "aur"}

router = APIRouter()


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if w not in _COMMON}


def relevant(memories: list[Memory], query: str, limit: int) -> list[Memory]:
    """The memories that share the most words with the query (newest first on ties)."""
    wanted = _words(query)
    scored = [(len(wanted & _words(m.content)), m.id, m) for m in memories]
    return [m for score, _, m in sorted(scored, key=lambda x: (-x[0], -x[1])) if score > 0][:limit]


def _line(m: Memory, tz_name: str) -> str:
    saved = m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=UTC)
    return f"- [{m.id}] (saved {saved.astimezone(zone(tz_name)).strftime('%d %b %Y')}) {m.content}"


def memories_for_prompt(query: str = "", tz_name: str = "UTC") -> str:
    with session_scope() as s:
        rows = list(s.scalars(select(Memory).where(Memory.archived_at.is_(None)).order_by(Memory.id.desc())))
        if not rows:
            return "(nothing yet)"
        note = ""
        if len(rows) > MAX_IN_PROMPT:
            total = len(rows)
            older = rows[NEWEST_IN_PROMPT:]
            fits = relevant(older, query, MAX_IN_PROMPT - NEWEST_IN_PROMPT)
            rest = [m for m in older if m not in fits][: MAX_IN_PROMPT - NEWEST_IN_PROMPT - len(fits)]  # then the next newest
            rows = rows[:NEWEST_IN_PROMPT] + fits + rest
            note = f"\n(Showing {len(rows)} of {total} memories: the newest and the ones that fit this message. Use recall_memory to search the rest.)"
        return "\n".join(_line(m, tz_name) for m in sorted(rows, key=lambda m: m.id)) + note


def search_memories(query: str, tz_name: str = "UTC", limit: int = 10) -> str:
    with session_scope() as s:
        found = relevant(list(s.scalars(select(Memory).where(Memory.archived_at.is_(None)))), query, limit)
        return "\n".join(_line(m, tz_name) for m in found) if found else "No saved memory matches that."


class MemoryOut(BaseModel):
    id: int
    content: str
    source_message_id: int | None
    created_at: datetime
    updated_at: datetime


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


def _out(m: Memory) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        content=m.content,
        source_message_id=m.source_message_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("/api/memories", response_model=list[MemoryOut])
def list_memories() -> list[MemoryOut]:
    with session_scope() as s:
        return [_out(m) for m in s.scalars(select(Memory).where(Memory.archived_at.is_(None)).order_by(Memory.id.desc()))]


class ArchivedOut(BaseModel):
    id: int
    content: str
    reason: str
    archived_at: datetime
    created_at: datetime


@router.get("/api/memories/archived", response_model=list[ArchivedOut])
def archived_memories() -> list[ArchivedOut]:
    with session_scope() as s:
        rows = s.scalars(select(Memory).where(Memory.archived_at.is_not(None)).order_by(Memory.archived_at.desc()))
        return [ArchivedOut(id=m.id, content=m.content, reason=m.archive_reason, archived_at=m.archived_at, created_at=m.created_at) for m in rows]


@router.post("/api/memories/{memory_id}/restore", response_model=MemoryOut)
def restore_memory(memory_id: int) -> MemoryOut:
    with session_scope() as s:
        memory = s.get(Memory, memory_id)
        if memory is None or memory.archived_at is None:
            raise HTTPException(404, f"Archived memory {memory_id} not found")
        memory.archived_at, memory.archive_reason = None, ""
        s.flush()
        out = _out(memory)
    audit("memory", "restored", detail={"id": memory_id, "content": out.content})
    return out


@router.post("/api/memories/tidy")
async def tidy_now(request: Request) -> dict:
    from junior.agent.builder import NoApiKeyError
    from junior.costs import BudgetExceeded
    from junior.memory_tidy import tidy_memories

    try:
        return await tidy_memories(request.app.state.registry, request.app.state.chat.model_provider, force=True)
    except (NoApiKeyError, BudgetExceeded) as e:
        raise HTTPException(409, str(e)) from None


@router.post("/api/memories", response_model=MemoryOut, status_code=201)
def add_memory(body: MemoryIn) -> MemoryOut:
    from junior.privacy import credential_present
    if credential_present(body.content):
        raise HTTPException(422, "Credentials belong in account/settings connections, never personal memory.")
    with session_scope() as s:
        memory = Memory(content=" ".join(body.content.split()))
        s.add(memory)
        s.flush()
        out = _out(memory)
    audit("memory", "added on Memory page", detail={"id": out.id, "content": out.content})
    return out


@router.patch("/api/memories/{memory_id}", response_model=MemoryOut)
def edit_memory(memory_id: int, body: MemoryIn) -> MemoryOut:
    from junior.privacy import credential_present
    if credential_present(body.content):
        raise HTTPException(422, "Credentials belong in account/settings connections, never personal memory.")
    with session_scope() as s:
        memory = s.get(Memory, memory_id)
        if memory is None:
            raise HTTPException(404, f"Memory {memory_id} not found")
        before = memory.content
        memory.content = " ".join(body.content.split())
        s.flush()
        out = _out(memory)
    audit("memory", "edited", detail={"id": memory_id, "before": before, "after": out.content})
    return out


@router.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: int) -> None:
    with session_scope() as s:
        memory = s.get(Memory, memory_id)
        if memory is None:
            raise HTTPException(404, f"Memory {memory_id} not found")
        content = memory.content
        s.delete(memory)
    audit("memory", "deleted", detail={"id": memory_id, "content": content})
