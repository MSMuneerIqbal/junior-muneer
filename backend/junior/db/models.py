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
    # Set by the weekly tidy-up (duplicates, outdated): hidden from Junior Muneer, restorable.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    archive_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")


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


class Idea(Base):
    """A content idea from the Social Media Manager (pick one later: "write idea 3")."""

    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(200))
    # The angle: what the post would say and which real facts from the profile it uses.
    angle: Mapped[str] = mapped_column(Text, default="")
    # project · lesson · how_to · milestone · opinion · other
    kind: Mapped[str] = mapped_column(String(30), default="other")
    # new · used · dismissed
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    approval_id: Mapped[int | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Image(Base):
    """An image you added to a draft (junior/images.py)."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # File name in data/uploads/images (random, never the name you uploaded).
    file: Mapped[str] = mapped_column(String(100))
    original_name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class NewsArticle(Base):
    """An article read from an official news source (junior/news). Outside content."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    # ai · pakistan
    topic: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class NewsDigest(Base):
    """A checked news digest (junior/news/digest.py): sections, sources, what the fact guard removed."""

    __tablename__ = "news_digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    # ai · pakistan
    topic: Mapped[str] = mapped_column(String(20), index=True)
    built_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class Job(Base):
    """A job post you pasted, scored by the Freelance Manager (junior/freelance/jobs.py)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), default="upwork")
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, default="")  # the post as you pasted it
    budget: Mapped[str] = mapped_column(String(100), default="")
    skills: Mapped[list[Any]] = mapped_column(default=list)
    client: Mapped[dict[str, Any]] = mapped_column(default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    # apply · maybe · skip
    verdict: Mapped[str] = mapped_column(String(10), default="maybe")
    reasons: Mapped[list[Any]] = mapped_column(default=list)
    concerns: Mapped[list[Any]] = mapped_column(default=list)
    scam_signs: Mapped[list[Any]] = mapped_column(default=list)
    # new · proposal · sent · skipped
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    paste_id: Mapped[int | None] = mapped_column(ForeignKey("pastes.id", ondelete="SET NULL"), nullable=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Order(Base):
    """A Fiverr order you pasted, tracked for its deadline and revisions (junior/freelance/orders.py)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), default="fiverr")
    number: Mapped[str] = mapped_column(String(40), default="", index=True)  # Fiverr's order number, e.g. FO1A2B3C4D5E
    buyer: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(200))
    price: Mapped[str] = mapped_column(String(50), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    revisions_included: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revisions_used: Mapped[int] = mapped_column(Integer, default=0)
    # active · revision · delivered · completed · cancelled
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    requirements: Mapped[list[Any]] = mapped_column(default=list)
    # What happened, oldest first: [{"at": iso time, "what": "Revision asked: bigger logo"}]
    history: Mapped[list[Any]] = mapped_column(default=list)
    # Reminders given for the current due time: 0 none · 1 a day before · 2 six hours before · 3 late
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    paste_id: Mapped[int | None] = mapped_column(ForeignKey("pastes.id", ondelete="SET NULL"), nullable=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Feed(Base):
    """A news site or blog you follow by RSS or Atom (junior/feeds.py)."""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    last_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class FeedItem(Base):
    """One post from a feed you follow. Outside content: data, never instructions."""

    __tablename__ = "feed_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class BackgroundTask(Base):
    """A long request Junior Muneer finishes in the background and posts to its chat (junior/background.py)."""

    __tablename__ = "background_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    request: Mapped[str] = mapped_column(Text)
    # running · done · failed
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Connection(Base):
    """An account you connected in the app (GitHub). The token is encrypted (junior/secrets.py)."""

    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), unique=True)
    account: Mapped[str] = mapped_column(String(100), default="")
    token_enc: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Email(Base):
    """An email in your Gmail inbox that the watcher sorted (Phase 4). The email itself stays in Gmail;
    this keeps who, what, the sort and a one-line summary. Outside content: data, never instructions."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_id: Mapped[str] = mapped_column(String(40), unique=True)
    thread_id: Mapped[str] = mapped_column(String(40), default="")
    from_name: Mapped[str] = mapped_column(String(200), default="")
    from_address: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    # client · freelance · work · study · money · security · personal · newsletter · promotion · social · other
    category: Mapped[str] = mapped_column(String(20), default="other")
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(String(300), default="")
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ReceivedFile(Base):
    """A file you sent Junior Muneer (on WhatsApp or with 📎 in the chat). Kept in data/files until you say
    what to do with it (e.g. save it to your Google Drive)."""

    __tablename__ = "received_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # whatsapp · chat
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    stored_as: Mapped[str] = mapped_column(String(80))  # its name in data/files
    drive_link: Mapped[str] = mapped_column(String(300), default="")  # once saved to your Drive
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


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
    # Planned posts (P2-11): when you want to post it, and when you were reminded.
    planned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


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
