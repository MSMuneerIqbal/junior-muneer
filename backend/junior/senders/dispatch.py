"""Sending one approved item (P3-01): Safety Guard -> run at most once -> sender -> record.

Nothing is ever retried by itself. "failed" (clearly not posted) leaves the item approved so you
can try again on purpose; "unclear" marks it "check manually" until you say whether it posted.
"""

import asyncio
import logging
from pathlib import Path

from junior.approvals import PLATFORM_LABELS, ApprovalError, ApprovalOut, to_out
from junior.audit import audit
from junior.db import ApprovalItem, session_scope
from junior.db.models import utcnow
from junior.permissions import AlreadyRun, claim_run, finish_run
from junior.senders.base import Outgoing, SendResult
from junior.senders.guard import check
from junior.senders.registry import SenderRegistry

log = logging.getLogger(__name__)

SEND_SECONDS = 60


class SendError(Exception):
    """Sending was blocked or isn't possible. The message says why, in plain words."""


def _images(item_id: int) -> tuple[Path, ...]:
    """The image files attached to an item, in the order you added them."""
    from sqlalchemy import select

    from junior.db import Image
    from junior.images import images_dir

    with session_scope() as s:
        names = s.scalars(select(Image.file).where(Image.approval_id == item_id).order_by(Image.id)).all()
    return tuple(images_dir() / n for n in names)


async def send_item(item_id: int, senders: SenderRegistry) -> ApprovalOut:
    """Send one approved API item now. Raises SendError when it's blocked or can't be sent."""
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        if item is None:
            raise LookupError(f"Approval item {item_id} doesn't exist.")
        text = item.meta.get("approved_text", "")
        if item.meta.get("sending_at"):
            raise SendError("It's being sent right now. It won't be sent twice.")
        problems = check(item, text)
        label = PLATFORM_LABELS.get(item.platform, item.platform)
        sender = senders.for_action(item.action_type) if item.action_type else None
        if not problems and sender is None:
            problems.append(f"{label} isn't connected yet. Connect it in Settings, or copy it and post it yourself.")
        if problems:
            # Saved before raising: raising inside this block would undo it, and the card couldn't show why.
            item.meta = {**item.meta, "blocked": problems}
            action_type = item.action_type
        else:
            attempt = int(item.meta.get("attempts", 0)) + 1
            out = Outgoing(item.id, item.action_type, item.platform, item.item_type, text, _images(item.id), dict(item.meta))
    if problems:
        audit("action", "send_blocked", result="blocked", detail={"id": item_id, "type": action_type, "problems": problems})
        raise SendError(problems[0])

    try:
        run_id = claim_run(f"approval-{item_id}-attempt-{attempt}", out.action_type)
    except AlreadyRun:
        raise SendError("It's already being sent (or was sent). It won't be sent twice.") from None
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        item.meta = {**item.meta, "attempts": attempt, "blocked": [], "sending_at": utcnow().isoformat()}

    try:
        result = await asyncio.wait_for(sender.send(out), SEND_SECONDS)
    except TimeoutError:
        result = SendResult("unclear", f"{sender.label} didn't answer in {SEND_SECONDS} seconds; it may or may not have posted.")
    except Exception as e:  # never retry: we can't know whether it went out
        log.exception("Sending item %s failed", item_id)
        result = SendResult("unclear", f"Something went wrong while sending to {sender.label} ({type(e).__name__}).")

    finish_run(run_id, {"sent": "done", "failed": "failed", "unclear": "check_manually"}[result.outcome],
               {"detail": result.detail, "remote_id": result.remote_id, "url": result.url})
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        meta = {k: v for k, v in item.meta.items() if k != "sending_at"}
        if result.outcome == "sent":
            item.status = "posted"
            item.posted_at = utcnow()
            meta.update(remote_id=result.remote_id, post_url=result.url, sent_text=out.text, last_error="")
        elif result.outcome == "failed":
            meta["last_error"] = result.detail  # still approved: you may try again on purpose
        else:
            item.status = "check_manually"
            meta["last_error"] = result.detail
        item.meta = meta
        item.updated_at = utcnow()
        s.flush()
        final = to_out(item)
    audit(
        "action",
        {"sent": "posted", "failed": "send_failed", "unclear": "check_manually"}[result.outcome],
        result="ok" if result.outcome == "sent" else "error",
        detail={"id": item_id, "type": out.action_type, "attempt": attempt, "detail": result.detail, "url": result.url},
        conversation_id=final.conversation_id,
    )
    return final


def recover_interrupted_sends() -> int:
    """At startup: a send the app was in the middle of when it stopped can't be known, so check it."""
    from sqlalchemy import select

    from junior.db import ActionRun

    count = 0
    with session_scope() as s:
        for item in s.scalars(select(ApprovalItem).where(ApprovalItem.kind == "api")):
            if item.meta.get("sending_at"):
                item.status = "check_manually"
                item.meta = {
                    **{k: v for k, v in item.meta.items() if k != "sending_at"},
                    "last_error": "The app stopped while sending this. Check the platform to see if it posted.",
                }
                count += 1
        for run in s.scalars(select(ActionRun).where(ActionRun.status == "running")):
            run.status = "check_manually"
            run.finished_at = utcnow()
    if count:
        audit("action", "interrupted_sends", result="error", detail={"items": count})
    return count


def resolve_unclear(item_id: int, posted: bool) -> ApprovalOut:
    """After "check manually": you tell us whether it really went out."""
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        if item is None:
            raise LookupError(f"Approval item {item_id} doesn't exist.")
        if item.status != "check_manually":
            raise ApprovalError("This item doesn't need checking.")
        if posted:
            item.status = "posted"
            item.posted_at = utcnow()
            item.meta = {**item.meta, "resolved_by": "you", "last_error": ""}
        else:
            item.status = "approved"  # you can send it again, on purpose
            item.meta = {**item.meta, "resolved_by": "you"}
        item.updated_at = utcnow()
        s.flush()
        out = to_out(item)
    audit("action", "checked_manually", detail={"id": item_id, "posted": posted})
    return out
