"""What happened (P7-03): a full, correct report of a day or a week, and the morning briefing.

The facts come from the database, never from the AI's memory; Junior Muneer and the briefing
writer only put them into words.

    GET  /api/report?period=today|yesterday|week   the facts, as text
    GET  /api/briefing/today                       today's briefing chat, if made
    POST /api/briefing/now                         make today's briefing now (once a day)
"""

import logging
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from junior.audit import audit
from junior.db import (
    ApprovalItem,
    AuditLog,
    BackgroundTask,
    Conversation,
    Idea,
    Job,
    Memory,
    Message,
    Order,
    Usage,
    session_scope,
)
from junior.settings_store import all_settings
from junior.timeutil import start_of_today_utc, zone

log = logging.getLogger(__name__)
router = APIRouter()
Period = Literal["today", "yesterday", "week"]
LABELS = {"linkedin": "LinkedIn", "facebook": "Facebook", "instagram": "Instagram", "x": "X", "upwork": "Upwork", "fiverr": "Fiverr"}


def period_bounds(period: Period, tz_name: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    today = start_of_today_utc(tz_name, now)
    if period == "yesterday":
        return today - timedelta(days=1), today
    if period == "week":
        return today - timedelta(days=6), now
    return today, now


def _local(dt: datetime, tz_name: str) -> str:
    return dt.astimezone(zone(tz_name)).strftime("%a %d %b, %H:%M")


def _titles(rows: list[str], limit: int = 5) -> str:
    shown = ", ".join(f"“{t}”" for t in rows[:limit])
    return shown + (f" and {len(rows) - limit} more" if len(rows) > limit else "")


def _kind(platform: str, item_type: str) -> str:
    return f"{LABELS.get(platform, platform)} {item_type}"


def day_facts(period: Period, tz_name: str, now: datetime | None = None) -> str:
    """Everything that happened in the period, from the database, as short sections of facts."""
    start, end = period_bounds(period, tz_name, now)
    now = now or datetime.now(UTC)
    present = period != "yesterday"  # "waiting now" and "due soon" belong to today's and the week's reports
    sections: list[tuple[str, list[str]]] = []
    with session_scope() as s:

        def between(col):
            return (col >= start) & (col < end)

        # Chats
        mine = s.scalars(select(Message).where(between(Message.created_at), Message.source == "user")).all()
        convo_ids = {m.conversation_id for m in mine}
        convos = s.scalars(select(Conversation).where(Conversation.id.in_(convo_ids))).all() if convo_ids else []
        calls = [c for c in convos if c.kind == "call"]
        voice = sum(1 for m in mine if m.audio_file)
        chat = []
        if mine:
            line = f"{len(convo_ids)} chat{'s' * (len(convo_ids) != 1)}, {len(mine)} message{'s' * (len(mine) != 1)} from you"
            line += f" ({voice} by voice)" if voice else ""
            line += f", {len(calls)} live call{'s' * (len(calls) != 1)}" if calls else ""
            chat.append(line + ".")
            topics = [c.title for c in convos if c.kind not in ("call", "briefing")]  # call titles are just a time
            if topics:
                chat.append("Topics: " + _titles(topics) + ".")
        sections.append(("Chats", chat))

        # Drafts and posting
        made = s.scalars(select(ApprovalItem).where(between(ApprovalItem.created_at))).all()
        posted = s.scalars(select(ApprovalItem).where(between(ApprovalItem.posted_at), ApprovalItem.status == "posted")).all()
        rejected = s.scalars(
            select(ApprovalItem).where(between(ApprovalItem.decided_at), ApprovalItem.status == "rejected")
        ).all()
        waiting = s.scalar(select(func.count()).select_from(ApprovalItem).where(ApprovalItem.status.in_(("waiting", "check_manually")))) or 0
        drafts = []
        if made:
            counts = Counter(_kind(a.platform, a.item_type) for a in made)
            drafts.append(f"{len(made)} draft{'s' * (len(made) != 1)} made: " + ", ".join(f"{k} ({n})" for k, n in counts.items()) + ".")
        if posted:
            drafts.append("Marked as posted or sent: " + _titles([f"{_kind(a.platform, a.item_type)}: {a.title}" for a in posted]) + ".")
        if rejected:
            drafts.append(f"Rejected: {len(rejected)}.")
        if waiting and present:
            drafts.append(f"Waiting for your OK right now: {waiting}.")
        sections.append(("Drafts and posting", drafts))

        # Freelance
        jobs = s.scalars(select(Job).where(between(Job.created_at))).all()
        sent_jobs = s.scalars(select(Job).where(between(Job.updated_at), Job.status == "sent")).all()
        new_orders = s.scalars(select(Order).where(between(Order.created_at))).all()
        delivered = [o for o in s.scalars(select(Order).where(between(Order.updated_at))) if o.status in ("delivered", "completed")]
        soon = s.scalars(
            select(Order).where(Order.status.in_(("active", "revision")), Order.due_at.is_not(None), Order.due_at <= now + timedelta(days=2))
            .order_by(Order.due_at)
        ).all() if present else []
        work = []
        if jobs:
            work.append("Jobs scored: " + ", ".join(f"“{j.title}” {j.score}/10 {j.verdict}" for j in jobs[:6]) + ".")
        if sent_jobs:
            work.append("Proposals marked as sent: " + _titles([j.title for j in sent_jobs]) + ".")
        if new_orders:
            work.append("Orders saved: " + _titles([o.title for o in new_orders]) + ".")
        if delivered:
            work.append("Orders delivered or completed: " + _titles([o.title for o in delivered]) + ".")
        for o in soon:
            when = f"late since {_local(o.due_at, tz_name)}" if o.due_at < now else f"due {_local(o.due_at, tz_name)}"
            work.append(f"Open order “{o.title}”: {when}.")
        sections.append(("Freelance", work))

        # Social
        ideas = s.scalars(select(Idea).where(between(Idea.created_at))).all()
        planned = s.scalars(
            select(ApprovalItem).where(
                ApprovalItem.planned_at.is_not(None), ApprovalItem.status.in_(("waiting", "approved")),
                ApprovalItem.planned_at < start_of_today_utc(tz_name, now) + timedelta(days=2),
            )
        ).all() if present else []
        social = []
        if ideas:
            social.append(f"Post ideas saved: {len(ideas)} (" + ", ".join(sorted({LABELS.get(i.platform, i.platform) for i in ideas})) + ").")
        for p in planned:
            social.append(f"Planned {_kind(p.platform, p.item_type)} “{p.title}” for {_local(p.planned_at, tz_name)}.")
        sections.append(("Social", social))

        # Memory
        remembered = s.scalars(select(Memory).where(between(Memory.created_at))).all()
        forgot = s.scalar(
            select(func.count()).select_from(AuditLog).where(between(AuditLog.created_at), AuditLog.kind == "memory", AuditLog.name == "deleted")
        ) or 0
        memory = [f"Remembered: {_titles([m.content for m in remembered], 4)}."] if remembered else []
        if forgot:
            memory.append(f"Forgot {forgot} thing{'s' * (forgot != 1)}.")
        sections.append(("Memory", memory))

        # Background work
        tasks = s.scalars(select(BackgroundTask).where(between(BackgroundTask.created_at))).all()
        background = [f"{t.status.capitalize()}: “{t.title}”." for t in tasks]
        sections.append(("Background work", background))

        # Spend
        spend = s.execute(select(Usage.mode, func.sum(Usage.cost_usd)).where(between(Usage.created_at)).group_by(Usage.mode)).all()
        total = sum(c or 0 for _, c in spend)
        money = [f"${total:.2f} on AI (" + ", ".join(f"{m} ${c:.2f}" for m, c in spend if c) + ")."] if total >= 0.005 else []
        sections.append(("Spend", money))

    span = f"{_local(start, tz_name)} to {_local(min(end, now), tz_name)}"
    shown = [f"## {title}\n" + "\n".join(f"- {line}" for line in lines) for title, lines in sections if lines]
    if not shown:
        return f"# What happened: {period} ({span}, your time zone)\nNothing recorded: no chats, drafts, jobs, orders or memories."
    return f"# What happened: {period} ({span}, your time zone)\n\n" + "\n\n".join(shown)


def news_headlines(limit: int = 3) -> str:
    from junior.news.digest import latest_digest

    lines = []
    for topic, label in (("ai", "AI news"), ("pakistan", "Pakistan")):
        digest = latest_digest(topic)
        items = [i for sec in (digest or {}).get("sections", []) for i in sec.get("items", [])]
        if items:
            lines.append(f"{label}: " + "; ".join(i["headline"] for i in items[:limit]) + ".")
    return "\n".join(f"- {line}" for line in lines)


# ---- the morning briefing --------------------------------------------------------


def briefing_today(tz_name: str, now: datetime | None = None) -> int | None:
    """Today's briefing chat, if it's been made."""
    with session_scope() as s:
        return s.scalar(
            select(Conversation.id).where(Conversation.kind == "briefing", Conversation.created_at >= start_of_today_utc(tz_name, now))
            .order_by(Conversation.id.desc())
        )


def briefing_prompt(settings: dict, now: datetime | None = None) -> str:
    tz = settings["timezone"]
    parts = [
        f"## Morning briefing facts for {settings['user_name']} ({_local(now or datetime.now(UTC), tz)}, their time zone)",
        "### Yesterday\n" + day_facts("yesterday", tz, now),
        "### Today so far and what's next\n" + day_facts("today", tz, now),
    ]
    if headlines := news_headlines():
        parts.append("### Latest news headlines (from today's digests)\n" + headlines)
    return "\n\n".join(parts)


async def make_briefing(registry, provider_factory, force: bool = False) -> int | None:
    """Write today's briefing (once a day) and save it as a chat. Returns the chat id."""
    from junior.agent.context import TurnContext
    from junior.agent.helpers import HelperRunner
    from junior.chat.history import save_usage
    from junior.costs import budget_left

    settings = all_settings()
    if not force and (existing := briefing_today(settings["timezone"])):
        return existing
    budget_left(settings)  # stop before spending anything if the cap is reached
    provider = provider_factory()  # no API key: says so
    context = TurnContext(conversation_id=None, settings=settings)
    context.mark_outside()  # news headlines are outside content
    text = await HelperRunner(registry, provider).run("briefing", briefing_prompt(settings), context)
    cost = round(sum(u.cost_usd for u in context.usage), 6)
    title = "☀ Morning briefing · " + datetime.now(UTC).astimezone(zone(settings["timezone"])).strftime("%a %d %b")
    with session_scope() as s:
        convo = Conversation(title=title, kind="briefing")
        s.add(convo)
        s.flush()
        message = Message(conversation_id=convo.id, role="assistant", source="assistant", content=text, steps=[], cost_usd=cost)
        s.add(message)
        s.flush()
        save_usage(s, context.usage, convo.id, message.id, mode="briefing")
        convo_id = convo.id
    audit("agent_run", "briefing", detail={"conversation_id": convo_id}, cost_usd=cost, conversation_id=convo_id)
    return convo_id


def briefing_due(settings: dict, now: datetime | None = None) -> bool:
    if not settings.get("briefing_enabled", True):
        return False
    tz = settings["timezone"]
    now = now or datetime.now(UTC)
    try:
        hour, minute = (int(x) for x in str(settings.get("briefing_time", "08:00")).split(":"))
    except ValueError:
        hour, minute = 8, 0
    local = now.astimezone(zone(tz))
    at = datetime.combine(local.date(), time(hour, minute), tzinfo=zone(tz))
    return local >= at and briefing_today(tz, now) is None


async def morning_briefing(registry, provider_factory) -> None:
    """Scheduler job: the briefing, once a day, at your briefing time (not while paused)."""
    from junior.agent.builder import NoApiKeyError
    from junior.costs import BudgetExceeded
    from junior.pause import is_paused

    if is_paused() or not briefing_due(all_settings()):
        return
    try:
        await make_briefing(registry, provider_factory)
    except (BudgetExceeded, NoApiKeyError) as e:
        log.info("Morning briefing skipped: %s", e)
    except Exception:
        log.exception("Morning briefing failed; will try again in a few minutes")


# ---- API ----------------------------------------------------------------------


@router.get("/api/report")
def report(period: str = "today") -> dict:
    if period not in ("today", "yesterday", "week"):
        raise HTTPException(422, "period must be today, yesterday or week")
    return {"period": period, "facts": day_facts(period, all_settings()["timezone"])}  # type: ignore[arg-type]


@router.get("/api/briefing/today")
def briefing_get() -> dict:
    return {"conversation_id": briefing_today(all_settings()["timezone"])}


@router.post("/api/briefing/now")
async def briefing_now(request: Request) -> dict:
    from junior.agent.builder import NoApiKeyError
    from junior.costs import BudgetExceeded

    try:
        convo = await make_briefing(request.app.state.registry, request.app.state.chat.model_provider)
    except (NoApiKeyError, BudgetExceeded) as e:
        raise HTTPException(409, str(e)) from None
    return {"conversation_id": convo}

