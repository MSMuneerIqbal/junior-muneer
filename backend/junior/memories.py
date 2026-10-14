"""Long-term memories about you: storage helpers and the REST API.

    GET    /api/memories         list (newest first)
    POST   /api/memories         add one yourself
    PATCH  /api/memories/{id}    edit
    DELETE /api/memories/{id}    delete (also the "undo" on a "Memory updated" note)
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.audit import audit
from junior.db import Memory, session_scope

# How many memories go into Junior Muneer's instructions each turn.
MAX_IN_PROMPT = 100

router = APIRouter()


def memories_for_prompt() -> str:
    with session_scope() as s:
        rows = s.scalars(select(Memory).order_by(Memory.id.desc()).limit(MAX_IN_PROMPT)).all()
        if not rows:
            return "(nothing yet)"
        return "\n".join(f"- [{m.id}] {m.content}" for m in reversed(rows))


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
        return [_out(m) for m in s.scalars(select(Memory).order_by(Memory.id.desc()))]


@router.post("/api/memories", response_model=MemoryOut, status_code=201)
def add_memory(body: MemoryIn) -> MemoryOut:
    with session_scope() as s:
        memory = Memory(content=" ".join(body.content.split()))
        s.add(memory)
        s.flush()
        out = _out(memory)
    audit("memory", "added on Memory page", detail={"id": out.id, "content": out.content})
    return out


@router.patch("/api/memories/{memory_id}", response_model=MemoryOut)
def edit_memory(memory_id: int, body: MemoryIn) -> MemoryOut:
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
