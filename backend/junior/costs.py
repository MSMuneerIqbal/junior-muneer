"""Spending and the daily safety cap.

    GET /api/usage/today        today's spend (your time zone), split by mode and agent, and the cap
    GET /api/usage/daily?days=  spend per day, newest first
"""

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from junior.db import Usage, session_scope
from junior.settings_store import all_settings
from junior.timeutil import start_of_today_utc, zone

router = APIRouter()


class BudgetExceeded(Exception):
    """The daily cap is reached: no new AI work until tomorrow (or a higher cap)."""


def spend_today(tz_name: str) -> float:
    since = start_of_today_utc(tz_name)
    with session_scope() as s:
        total = s.scalar(select(func.sum(Usage.cost_usd)).where(Usage.created_at >= since))
    return float(total or 0.0)


def budget_left(settings: dict | None = None) -> float:
    """Dollars left today. Raises BudgetExceeded when nothing is left."""
    settings = settings or all_settings()
    cap = float(settings["daily_cap_usd"])
    spent = spend_today(settings["timezone"])
    if spent >= cap:
        raise BudgetExceeded(
            f"Daily safety cap reached: ${spent:.2f} spent today, cap is ${cap:.2f}. "
            "New AI work is stopped until midnight your time. "
            "You can raise the cap in Settings."
        )
    return cap - spent


@router.get("/api/usage/today")
def usage_today() -> dict:
    settings = all_settings()
    since = start_of_today_utc(settings["timezone"])
    with session_scope() as s:
        by_mode = dict(
            s.execute(
                select(Usage.mode, func.sum(Usage.cost_usd))
                .where(Usage.created_at >= since)
                .group_by(Usage.mode)
            ).all()
        )
        by_agent = dict(
            s.execute(
                select(Usage.agent, func.sum(Usage.cost_usd))
                .where(Usage.created_at >= since)
                .group_by(Usage.agent)
            ).all()
        )
    spent = sum(by_mode.values())
    cap = float(settings["daily_cap_usd"])
    return {
        "spent_usd": round(spent, 6),
        "cap_usd": cap,
        "left_usd": round(max(cap - spent, 0.0), 6),
        "cap_reached": spent >= cap,
        "by_mode": {k: round(v, 6) for k, v in by_mode.items()},
        "by_agent": {k: round(v, 6) for k, v in by_agent.items()},
    }


@router.get("/api/usage/daily")
def usage_daily(days: int = 7) -> list[dict]:
    settings = all_settings()
    days = max(1, min(days, 365))
    tz = zone(settings["timezone"])
    since = start_of_today_utc(settings["timezone"]) - timedelta(days=days - 1)
    totals: dict[str, float] = defaultdict(float)
    with session_scope() as s:
        for created, cost in s.execute(
            select(Usage.created_at, Usage.cost_usd).where(Usage.created_at >= since)
        ):
            totals[created.astimezone(tz).date().isoformat()] += cost
    return [{"date": d, "spent_usd": round(totals[d], 6)} for d in sorted(totals, reverse=True)]
