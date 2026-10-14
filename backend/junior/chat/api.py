"""Chat API.

REST (chats):
    GET    /api/conversations?q=&limit=      list (pinned first, newest first), search
    POST   /api/conversations                create an empty chat
    PATCH  /api/conversations/{id}           rename / pin
    DELETE /api/conversations/{id}           delete with its messages
    GET    /api/conversations/{id}/messages  read messages

WebSocket /ws/chat:
    you send   {"type": "message", "conversation_id": 12 | null, "text": "...",
                "audio_id": "<from /api/voice/transcribe>", "audio_seconds": 4.2}  (audio: voice only)
    you get    conversation · user_message · delta · step · memory · done · error events
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from junior.db import Conversation, Message, Usage, session_scope

log = logging.getLogger(__name__)
router = APIRouter()


class ConversationOut(BaseModel):
    id: int
    title: str
    kind: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageOut(BaseModel):
    id: int
    role: str
    source: str
    content: str
    steps: list[Any]
    cost_usd: float
    audio_file: str | None = None
    audio_seconds: float | None = None
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", max_length=200)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None


def _out(convo: Conversation, count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=convo.id,
        title=convo.title,
        kind=convo.kind,
        pinned=convo.pinned,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
        message_count=count,
    )


@router.get("/api/conversations", response_model=list[ConversationOut])
def list_conversations(q: str = "", limit: int = 200) -> list[ConversationOut]:
    counts = (
        select(Message.conversation_id, func.count(Message.id).label("n"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    query = select(Conversation, func.coalesce(counts.c.n, 0)).join(
        counts, counts.c.conversation_id == Conversation.id, isouter=True
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        in_messages = select(Message.conversation_id).where(Message.content.ilike(pattern))
        query = query.where(or_(Conversation.title.ilike(pattern), Conversation.id.in_(in_messages)))
    query = query.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(
        max(1, min(limit, 1000))
    )
    with session_scope() as s:
        return [_out(c, n) for c, n in s.execute(query).all()]


@router.post("/api/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationCreate) -> ConversationOut:
    with session_scope() as s:
        convo = Conversation(title=body.title.strip() or "New chat")
        s.add(convo)
        s.flush()
        return _out(convo)


def _get_or_404(s, conversation_id: int) -> Conversation:
    convo = s.get(Conversation, conversation_id)
    if convo is None:
        raise HTTPException(404, f"Chat {conversation_id} not found")
    return convo


@router.patch("/api/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: int, body: ConversationUpdate) -> ConversationOut:
    with session_scope() as s:
        convo = _get_or_404(s, conversation_id)
        if body.title is not None:
            convo.title = body.title.strip()
        if body.pinned is not None:
            convo.pinned = body.pinned
        s.flush()
        return _out(convo, len(convo.messages))


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int) -> None:
    with session_scope() as s:
        s.delete(_get_or_404(s, conversation_id))


@router.get("/api/conversations/{conversation_id}/summary")
def conversation_summary(conversation_id: int) -> dict:
    """Total cost of a chat, and for a live call how long it lasted."""
    with session_scope() as s:
        convo = _get_or_404(s, conversation_id)
        rows = s.execute(
            select(Usage.agent, Usage.cost_usd, Usage.extra).where(
                Usage.conversation_id == conversation_id
            )
        ).all()
        kind = convo.kind
    seconds = sum(float(e.get("seconds", 0)) for a, _, e in rows if a == "live_call")
    return {
        "kind": kind,
        "cost_usd": round(sum(c for _, c, _ in rows), 6),
        "call_seconds": round(seconds, 1) if kind == "call" else None,
    }


@router.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def read_messages(conversation_id: int) -> list[MessageOut]:
    with session_scope() as s:
        _get_or_404(s, conversation_id)
        rows = s.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()
        return [
            MessageOut(
                id=m.id,
                role=m.role,
                source=m.source,
                content=m.content,
                steps=m.steps,
                cost_usd=m.cost_usd,
                audio_file=m.audio_file,
                audio_seconds=m.audio_seconds,
                created_at=m.created_at,
            )
            for m in rows
        ]


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    chat = websocket.app.state.chat
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict) or data.get("type") != "message":
                await websocket.send_json({"type": "error", "message": "Unknown request."})
                continue
            conversation_id = data.get("conversation_id")
            if conversation_id is not None and not isinstance(conversation_id, int):
                await websocket.send_json({"type": "error", "message": "Bad conversation_id."})
                continue
            audio_id = data.get("audio_id")
            audio_seconds = data.get("audio_seconds")
            async for event in chat.reply(
                conversation_id,
                str(data.get("text", "")),
                audio_id=audio_id if isinstance(audio_id, str) else None,
                audio_seconds=float(audio_seconds)
                if isinstance(audio_seconds, (int, float))
                else None,
            ):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        log.debug("Chat socket closed")
