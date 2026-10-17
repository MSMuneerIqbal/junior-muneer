"""The weekly memory tidy-up (P7-04): duplicates and outdated memories are archived, never deleted or rewritten.

A small model suggests which memories to archive and why; code checks every suggestion
(real, active memories only; "outdated" only for memories at least 2 weeks old or replaced
by a newer one; at most 30% of memories in one run). You see them under "Tidied up" on the
Memory page, each with its reason and a Restore button.
"""

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.audit import audit
from junior.db import Memory, session_scope
from junior.settings_store import all_settings, set_setting
from junior.timeutil import zone

log = logging.getLogger(__name__)
MIN_MEMORIES = 10  # the weekly run waits until there's something to tidy
EVERY = timedelta(days=7)
STALE_AFTER = timedelta(days=14)
MAX_SHARE = 0.3


class ArchivePick(BaseModel):
    id: int = Field(description="The memory to archive.")
    kind: Literal["duplicate", "outdated"]
    keep_id: int | None = Field(default=None, description="The memory that stays: the one it duplicates, or the newer one that replaces it.")
    reason: str = Field(description="One short sentence for the user.")


class TidyOut(BaseModel):
    archive: list[ArchivePick] = Field(default_factory=list)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def check_picks(picks: list[ArchivePick], active: dict[int, Memory], now: datetime) -> list[ArchivePick]:
    """Only safe suggestions pass: see the module docstring."""
    limit = max(1, math.floor(len(active) * MAX_SHARE))
    chosen: dict[int, ArchivePick] = {}
    exact: set[int] = set()  # duplicates with the same words, checked by code
    for pick in picks:
        memory = active.get(pick.id)
        keep = active.get(pick.keep_id) if pick.keep_id is not None else None
        if memory is None or pick.id in chosen or (pick.keep_id is not None and (keep is None or pick.keep_id == pick.id)):
            continue
        if keep is not None and pick.keep_id in chosen:
            continue  # the one to keep is being archived itself
        if pick.kind == "duplicate" and keep is None:
            continue
        if pick.kind == "outdated":
            replaced = keep is not None and _aware(keep.created_at) > _aware(memory.created_at)
            if not replaced and now - _aware(memory.created_at) < STALE_AFTER:
                continue  # too new to call outdated
        if not pick.reason.strip():
            continue
        same_words = keep is not None and _same(memory.content, keep.content)  # checked by code: always safe
        if not same_words and len(chosen) - len(exact) >= limit:
            continue
        if same_words:
            exact.add(pick.id)
        chosen[pick.id] = pick
    return list(chosen.values())


def _same(a: str, b: str) -> bool:
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())


def tidy_prompt(memories: list[Memory], tz_name: str, now: datetime) -> str:
    lines = "\n".join(
        f"[{m.id}] (saved {_aware(m.created_at).astimezone(zone(tz_name)).strftime('%d %b %Y')}) {m.content}" for m in memories
    )
    return f"## Memories\n{lines}\n\n## Today\n{now.astimezone(zone(tz_name)).strftime('%d %b %Y')}"


def tidy_due(settings: dict, now: datetime | None = None) -> bool:
    if not settings.get("memory_tidy_enabled", True):
        return False
    last = settings.get("memory_tidied_at") or ""
    if not last:
        return True
    try:
        return (now or datetime.now(UTC)) - datetime.fromisoformat(last) >= EVERY
    except ValueError:
        return True


async def tidy_memories(registry, provider_factory, force: bool = False, now: datetime | None = None) -> dict:
    """Archive duplicate and outdated memories. Returns what was archived, and the cost."""
    from junior.agent.context import TurnContext
    from junior.agent.helpers import HelperRunner
    from junior.chat.history import save_usage
    from junior.costs import budget_left

    now = now or datetime.now(UTC)
    settings = all_settings()
    with session_scope() as s:
        memories = list(s.scalars(select(Memory).where(Memory.archived_at.is_(None)).order_by(Memory.id)))
        s.expunge_all()
    if len(memories) < (2 if force else MIN_MEMORIES):
        return {"archived": [], "cost_usd": 0.0, "message": "Not enough memories to tidy yet."}
    budget_left(settings)
    provider = provider_factory()
    context = TurnContext(conversation_id=None, settings=settings)
    raw: TidyOut = await HelperRunner(registry, provider).run_structured(
        "memory_tidier", tidy_prompt(memories, settings["timezone"], now), context, TidyOut
    )
    picks = check_picks(raw.archive, {m.id: m for m in memories}, now)
    cost = round(sum(u.cost_usd for u in context.usage), 6)
    archived = []
    with session_scope() as s:
        for pick in picks:
            memory = s.get(Memory, pick.id)
            memory.archived_at, memory.archive_reason = now, pick.reason.strip()[:300]
            archived.append({"id": pick.id, "content": memory.content, "reason": memory.archive_reason})
        save_usage(s, context.usage, None, None, mode="memory")
    set_setting("memory_tidied_at", now.isoformat())
    audit("memory", "tidied", detail={"archived": archived, "suggested": len(raw.archive)}, cost_usd=cost)
    message = (
        f"Tidied up: archived {len(archived)} memor{'y' if len(archived) == 1 else 'ies'}. You can restore any of them."
        if archived
        else "Everything looks tidy: nothing to archive."
    )
    return {"archived": archived, "cost_usd": cost, "message": message}


async def weekly_tidy(registry, provider_factory) -> None:
    """Scheduler job: once a week, when there are enough memories (not while paused)."""
    from junior.agent.builder import NoApiKeyError
    from junior.costs import BudgetExceeded
    from junior.pause import is_paused

    if is_paused() or not tidy_due(all_settings()):
        return
    try:
        result = await tidy_memories(registry, provider_factory)
        if not result["archived"] and result["cost_usd"] == 0:
            set_setting("memory_tidied_at", datetime.now(UTC).isoformat())  # checked: too few to tidy
    except (BudgetExceeded, NoApiKeyError) as e:
        log.info("Memory tidy-up skipped: %s", e)
    except Exception:
        log.exception("Memory tidy-up failed; will try again later")
