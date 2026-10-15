"""Tables. Times are stored in UTC."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores times as UTC and always reads them back time-zone aware.
    (SQLite drops the time zone, so without this they'd come back naive.)"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError("Naive datetime; use junior.db.models.utcnow()")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    # text · voice · call (phase 1) · whatsapp (phase 8)
    kind: Mapped[str] = mapped_column(String(20), default="text")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    # Summary of the older part of a long chat (P0-08), and the last message it covers.
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_upto_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # user · assistant
    role: Mapped[str] = mapped_column(String(20))
    # Where the text came from. "user" = your own words; "outside" = pasted text,
    # emails, web results, subagent reports; "assistant" = Junior Muneer.
    # Memories may only be saved from "user" messages (ground rule 6).
    source: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    # Steps behind an answer (tool calls, subagents) for "Show work".
    steps: Mapped[list[Any]] = mapped_column(default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # Voice (phase 1): the recording of a voice message, or the spoken reply,
    # as a file name in data/uploads/audio, and its length.
    audio_file: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    # The message of yours it was saved from (empty if you added it on the Memory page).
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, index=True
    )
    agent: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    # text · voice · call · tool
    mode: Mapped[str] = mapped_column(String(20), default="text")
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Extra billed units, e.g. web searches or audio seconds.
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, index=True
    )
    # agent_run · tool_call · memory · setting · system
    kind: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # ok · error · blocked
    result: Mapped[str] = mapped_column(String(20), default="ok")
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )


class Paste(Base):
    """Text you pasted from another site. Outside content: data, never instructions."""

    __tablename__ = "pastes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # linkedin · facebook · instagram · x · upwork · fiverr · email · other
    platform: Mapped[str] = mapped_column(String(30), index=True)
    # post · comment · job · client_message · email · other
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # The chat message that holds it (source = "outside").
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ApprovalItem(Base):
    """A draft waiting for you (junior/approvals.py)."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    # copy (you send it yourself) · api (sent through an official API after your OK)
    kind: Mapped[str] = mapped_column(String(10))
    platform: Mapped[str] = mapped_column(String(30), index=True)
    # post · comment · reply · proposal · message · email ...
    item_type: Mapped[str] = mapped_column(String(40))
    action_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    edits: Mapped[list[Any]] = mapped_column(default=list)
    # score, issues, image idea, the post it answers (source_url)...
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # waiting · approved · rejected · posted · check_manually
    status: Mapped[str] = mapped_column(String(20), index=True)
    from_outside: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(300), default="")
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ActionRun(Base):
    """"Run at most once": every outgoing action is claimed here by a unique key before it runs."""

    __tablename__ = "action_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True)
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    # running · done · failed · check_manually
    status: Mapped[str] = mapped_column(String(20), default="running")
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )
