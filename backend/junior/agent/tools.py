"""Tools an agent file can ask for, by name (see KNOWN_TOOLS in registry.py)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from agents import FunctionTool, RunContextWrapper, Tool, WebSearchTool, function_tool
from sqlalchemy import func, or_, select

from junior.agent.context import TurnContext
from junior.db import Conversation, Message, Usage, session_scope
from junior.timeutil import start_of_today_utc, zone

Ctx = RunContextWrapper[TurnContext]


# ---- database (read only) --------------------------------------------------


@function_tool
def recent_chats(ctx: Ctx, days: int = 7) -> str:
    """List your chats from the last few days: title, date and number of messages.

    Args:
        days: How many days back to look (1 to 90).
    """
    days = max(1, min(days, 90))
    tz = zone(ctx.context.settings["timezone"])
    since = start_of_today_utc(ctx.context.settings["timezone"]) - timedelta(days=days - 1)
    with session_scope() as s:
        rows = s.execute(
            select(Conversation.title, Conversation.updated_at, func.count(Message.id))
            .join(Message, isouter=True)
            .where(Conversation.updated_at >= since)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        ).all()
    if not rows:
        return f"No chats in the last {days} day(s)."
    return "\n".join(
        f"- {title} ({updated.astimezone(tz):%a %d %b %H:%M}, {count} messages)"
        for title, updated, count in rows
    )


@function_tool
def search_chats(ctx: Ctx, query: str) -> str:
    """Search your past chats for words or a phrase. Returns matching snippets.

    Args:
        query: The words to look for.
    """
    words = [w for w in query.split() if len(w) > 1][:5]
    if not words:
        return "Give me at least one word to search for."
    tz = zone(ctx.context.settings["timezone"])
    with session_scope() as s:
        rows = s.execute(
            select(Conversation.title, Message.role, Message.content, Message.created_at)
            .join(Conversation)
            .where(or_(*[Message.content.ilike(f"%{w}%") for w in words]))
            .where(Message.conversation_id != ctx.context.conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        ).all()
    if not rows:
        return f"Nothing found for {query!r}."
    # Past answers can contain web results, so treat them as outside text.
    ctx.context.mark_outside()
    lines = []
    for title, role, content, created in rows:
        who = "You" if role == "user" else "Junior Muneer"
        snippet = " ".join(content.split())[:240]
        lines.append(f'- [{title}, {created.astimezone(tz):%d %b}] {who}: "{snippet}"')
    return "\n".join(lines)


@function_tool
def spending(ctx: Ctx, period: Literal["today", "week", "month"] = "today") -> str:
    """How much the AI has cost, in US dollars, split by mode (text, voice, call).

    Args:
        period: today, week (last 7 days) or month (last 30 days).
    """
    tz_name = ctx.context.settings["timezone"]
    days = {"today": 0, "week": 6, "month": 29}[period]
    since = start_of_today_utc(tz_name) - timedelta(days=days)
    with session_scope() as s:
        rows = s.execute(
            select(Usage.mode, func.sum(Usage.cost_usd))
            .where(Usage.created_at >= since)
            .group_by(Usage.mode)
        ).all()
    total = sum(cost or 0 for _, cost in rows)
    parts = ", ".join(f"{mode} ${cost:.4f}" for mode, cost in rows) or "nothing yet"
    cap = ctx.context.settings["daily_cap_usd"]
    return f"Spend ({period}): ${total:.4f} ({parts}). Daily safety cap: ${cap:.2f}."


DATABASE_TOOLS: list[FunctionTool] = [recent_chats, search_chats, spending]


def _web_search() -> list[Tool]:
    return [WebSearchTool(search_context_size="medium")]


# Name in the agent file -> the tools it gives.
TOOL_FACTORIES: dict[str, Callable[[], list[Tool]]] = {
    "web_search": _web_search,
    "database": lambda: list(DATABASE_TOOLS),
}


def build_tools(names: tuple[str, ...]) -> list[Tool]:
    tools: list[Tool] = []
    for name in names:
        if name not in TOOL_FACTORIES:
            raise KeyError(f"Tool {name!r} is not available yet.")
        tools.extend(TOOL_FACTORIES[name]())
    return tools
