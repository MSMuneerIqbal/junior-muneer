"""Fiverr orders you paste (P5-08): deadlines, revisions, reminders and delivery messages.

    GET  /api/orders?status=open|all|active|revision|delivered|completed|cancelled
    GET  /api/orders/due              open orders due within 2 days, or late (the Today panel)
    POST /api/orders/{id}/status  {"status"}   you mark it delivered, completed, cancelled or active

The Freelance Manager reads a pasted order (save_order) and records revisions (update_order).
Due times are read in your time zone and kept in UTC. Reminders come a day and six hours
before the due time, and when it's late.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.audit import audit
from junior.db import Order, session_scope
from junior.db.models import utcnow
from junior.settings_store import get_setting
from junior.timeutil import zone

router = APIRouter()
STATUSES = ("active", "revision", "delivered", "completed", "cancelled")
OPEN = ("active", "revision")  # still to deliver
Status = Literal["active", "revision", "delivered", "completed", "cancelled"]
DUE_SOON = timedelta(days=2)  # shown on the Today panel from then on
# Reminder stages for the current due time: (stage, time left, words)
REMINDERS = [(1, timedelta(hours=24), "due within a day"), (2, timedelta(hours=6), "due within 6 hours"), (3, timedelta(0), "late")]


class OrderIn(BaseModel):
    """What the Freelance Manager reads from a pasted order."""

    number: str = Field(default="", description="The order number, like FO1A2B3C4D5E; empty if not shown.")
    buyer: str = Field(default="", description="The buyer's name or username.")
    title: str = Field(description="What the order is for: the gig title or a short summary.")
    price: str = Field(default="", description="The order's price as shown, like $120.")
    due: str = Field(
        default="",
        description="When it's due, in the user's time zone, as YYYY-MM-DD HH:MM. Work it out from a countdown "
        "like '2 days 5 hours left' using the current time. Empty if the paste doesn't say.",
    )
    revisions_included: int | None = Field(default=None, description="Revisions the order includes, if shown.")
    revisions_used: int | None = Field(default=None, description="Revisions already asked for, if shown.")
    status: Status = Field(
        default="active",
        description="active (in progress), revision (a revision was asked for), delivered, completed or cancelled.",
    )
    requirements: list[str] = Field(default_factory=list, description="What the buyer asked for, in 1 to 6 short points.")


class OrderOut(BaseModel):
    id: int
    platform: str
    number: str
    buyer: str
    title: str
    price: str
    url: str
    due_at: datetime | None
    revisions_included: int | None
    revisions_used: int
    status: str
    requirements: list[str]
    history: list[dict]
    approval_id: int | None
    created_at: datetime
    updated_at: datetime


class OrderError(ValueError):
    pass


def _out(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id, platform=o.platform, number=o.number, buyer=o.buyer, title=o.title, price=o.price, url=o.url,
        due_at=o.due_at, revisions_included=o.revisions_included, revisions_used=o.revisions_used, status=o.status,
        requirements=o.requirements, history=o.history, approval_id=o.approval_id, created_at=o.created_at,
        updated_at=o.updated_at,
    )


def parse_due(text: str, tz_name: str, now: datetime | None = None) -> datetime | None:
    """'YYYY-MM-DD HH:MM' in your time zone, as UTC. None if it can't be read or isn't believable."""
    try:
        local = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if local.tzinfo is None:
        local = local.replace(tzinfo=zone(tz_name))
    due = local.astimezone(UTC)
    now = now or utcnow()
    if not now - timedelta(days=60) <= due <= now + timedelta(days=365):
        return None  # a misread date
    return due


def _note(order: Order, what: str) -> None:
    order.history = [*order.history, {"at": utcnow().isoformat(timespec="seconds"), "what": what}][-50:]
    order.updated_at = utcnow()


def _set_due(order: Order, due: datetime | None) -> None:
    if due is not None and due != order.due_at:
        order.due_at = due
        order.reminder_stage = 0  # a new due time gets its own reminders


def save_order(data: OrderIn, url: str = "", platform: str = "fiverr", paste_id: int | None = None) -> tuple[OrderOut, bool, bool]:
    """Save a pasted order, or update it when the same order number was pasted before.

    Returns (order, is it new, was the due time read).
    """
    due = parse_due(data.due, get_setting("timezone")) if data.due.strip() else None
    number = re.sub(r"[^A-Za-z0-9-]", "", data.number).upper()[:40]
    with session_scope() as s:
        order = None
        if number:
            order = s.scalars(select(Order).where(Order.platform == platform, Order.number == number)).first()
        new = order is None
        if order is None:
            order = Order(platform=platform, number=number, title="", history=[], revisions_used=0, reminder_stage=0)
            s.add(order)
        order.title = data.title.strip()[:200] or order.title or "An order"
        order.buyer = data.buyer.strip()[:100] or order.buyer
        order.price = data.price.strip()[:50] or order.price
        if url.startswith(("https://", "http://")):
            order.url = url[:500]
        if data.requirements:
            order.requirements = [r.strip() for r in data.requirements if r.strip()][:6]
        if data.revisions_included is not None:
            order.revisions_included = max(0, data.revisions_included)
        if data.revisions_used is not None:
            order.revisions_used = max(0, data.revisions_used)
        order.status = data.status
        order.paste_id = paste_id or order.paste_id
        _set_due(order, due)
        _note(order, "Saved from your paste" if new else "Updated from your paste")
        s.flush()
        out = _out(order)
    audit("action", "order_saved", detail={"id": out.id, "number": out.number, "new": new, "due_at": str(out.due_at)})
    return out, new, due is not None


def update_order(
    order_id: int, status: str | None = None, due: str = "", revisions_used: int | None = None, note: str = ""
) -> OrderOut:
    """A change to an order: a revision asked for, a new due time, or a new status."""
    if status is not None and status not in STATUSES:
        raise OrderError(f"Status must be one of {', '.join(STATUSES)}.")
    new_due = None
    if due.strip():
        new_due = parse_due(due, get_setting("timezone"))
        if new_due is None:
            raise OrderError(f"Couldn't read the due time {due!r}. Give it as YYYY-MM-DD HH:MM in the user's time zone.")
    with session_scope() as s:
        order = s.get(Order, order_id)
        if order is None:
            raise OrderError(f"There's no order {order_id}.")
        changes = []
        if status == "revision" and order.status != "revision" and revisions_used is None:
            revisions_used = order.revisions_used + 1  # a new revision request
        if revisions_used is not None and revisions_used != order.revisions_used:
            order.revisions_used = max(0, revisions_used)
            changes.append(f"revisions used: {order.revisions_used}")
        if status is not None and status != order.status:
            order.status = status
            changes.append(f"status: {status}")
        if new_due is not None and new_due != order.due_at:
            _set_due(order, new_due)
            changes.append("new due time")
        _note(order, note.strip()[:200] or ("Changed " + ", ".join(changes) if changes else "Checked, nothing changed"))
        s.flush()
        out = _out(order)
    audit("action", "order_updated", detail={"id": out.id, "status": out.status, "note": note[:200]})
    return out


def get_order(order_id: int) -> OrderOut | None:
    with session_scope() as s:
        order = s.get(Order, order_id)
        return _out(order) if order else None


def link_delivery(order_id: int, approval_id: int) -> None:
    with session_scope() as s:
        order = s.get(Order, order_id)
        if order:
            order.approval_id = approval_id
            _note(order, "Delivery message drafted")


def delivery_sent(order_id: int) -> None:
    """The delivery message card was marked as sent: the order is delivered."""
    with session_scope() as s:
        order = s.get(Order, order_id)
        if order and order.status in OPEN:
            order.status = "delivered"
            _note(order, "Delivered: you sent the delivery message")


def open_orders(limit: int = 10) -> list[OrderOut]:
    """Orders still to deliver, soonest first (no due time last)."""
    with session_scope() as s:
        q = select(Order).where(Order.status.in_(OPEN)).order_by(Order.due_at.is_(None), Order.due_at).limit(limit)
        return [_out(o) for o in s.scalars(q)]


def due_text(due_at: datetime | None, tz_name: str, now: datetime | None = None) -> str:
    """'due Mon 20 Oct, 17:00 (in 1 day 4 hours)' in your time zone, or 'late by 3 hours'."""
    if due_at is None:
        return "no due time yet"
    now = now or utcnow()
    local = due_at.astimezone(zone(tz_name)).strftime("%a %d %b, %H:%M")
    left = due_at - now
    days, hours = divmod(int(abs(left).total_seconds() // 3600), 24)
    if days:
        span = f"{days} day{'s' * (days != 1)}" + (f" {hours} hour{'s' * (hours != 1)}" if hours else "")
    elif hours:
        span = f"{hours} hour{'s' * (hours != 1)}"
    else:
        span = "under an hour"
    return f"due {local} (late by {span})" if left < timedelta(0) else f"due {local} (in {span})"


def remind_orders(now: datetime | None = None) -> int:
    """Scheduler job: note orders that are due within a day, within 6 hours, or late."""
    from junior.pause import is_paused

    if is_paused():
        return 0
    now = now or utcnow()
    found = []
    with session_scope() as s:
        for order in s.scalars(select(Order).where(Order.status.in_(OPEN), Order.due_at.is_not(None))):
            left = order.due_at - now
            reached = [(stage, words) for stage, before, words in REMINDERS if left <= before]
            if reached and reached[-1][0] > order.reminder_stage:
                order.reminder_stage = reached[-1][0]
                found.append((order.id, order.title, reached[-1][1]))
    for order_id, title, words in found:
        audit("action", "order_reminder", detail={"id": order_id, "title": title, "when": words})
    return len(found)


# ---- API --------------------------------------------------------------------


@router.get("/api/orders", response_model=list[OrderOut])
def list_orders(status: str = "open", limit: int = 100) -> list[OrderOut]:
    if status not in ("open", "all", *STATUSES):
        raise HTTPException(422, f"status must be 'open', 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(Order).order_by(Order.id.desc()).limit(min(limit, 500))
        if status == "open":
            q = q.where(Order.status.in_(OPEN))
        elif status != "all":
            q = q.where(Order.status == status)
        return [_out(o) for o in s.scalars(q)]


@router.get("/api/orders/due", response_model=list[OrderOut])
def orders_due() -> list[OrderOut]:
    with session_scope() as s:
        q = (
            select(Order)
            .where(Order.status.in_(OPEN), Order.due_at.is_not(None), Order.due_at <= utcnow() + DUE_SOON)
            .order_by(Order.due_at)
        )
        return [_out(o) for o in s.scalars(q)]


class StatusIn(BaseModel):
    status: Status


@router.post("/api/orders/{order_id}/status", response_model=OrderOut)
def set_status(order_id: int, body: StatusIn) -> OrderOut:
    try:
        return update_order(order_id, status=body.status, note=f"You marked it {body.status}")
    except OrderError as e:
        raise HTTPException(404 if "no order" in str(e) else 422, str(e)) from None
