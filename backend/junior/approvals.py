"""The approval queue: every draft that leaves the system waits here for you.

Two kinds of items:
    copy   you send it yourself (copy, open the platform, paste, then "Mark as posted").
           Upwork, Fiverr, LinkedIn comments, X... The system never sends these.
    api    sent through an official API (phase 3), only after your OK or your Auto rule.

Status: waiting · approved · rejected · posted · check_manually
Every edit is kept (the original text and each change).

    GET  /api/approvals?status=waiting|approved|rejected|posted|check_manually|all&platform=linkedin
    GET  /api/approvals/count             {"waiting": n}
    GET  /api/approvals/{id}
    POST /api/approvals                   add a copy-and-paste draft (API items come only from agents)
    PATCH /api/approvals/{id}  {"text"}   edit (while waiting)
    POST /api/approvals/{id}/approve  {"always_allow": bool}   API items
    POST /api/approvals/{id}/posted       copy items: you posted it
    POST /api/approvals/{id}/reject
    POST /api/approvals/{id}/restore      undo a reject
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from junior.audit import audit
from junior.db import ApprovalItem, session_scope
from junior.db.models import utcnow
from junior.permissions import decide, set_rule

router = APIRouter()

STATUSES = ("waiting", "approved", "rejected", "posted", "check_manually")
Kind = Literal["copy", "api"]

# Where "Open platform" goes when the item doesn't link to a specific post.
OPEN_URLS = {
    "linkedin": "https://www.linkedin.com/feed/",
    "facebook": "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "x": "https://x.com/compose/post",
    "upwork": "https://www.upwork.com/nx/find-work/",
    "fiverr": "https://www.fiverr.com/inbox",
    "email": "https://mail.google.com/",
    "github": "https://github.com/",
}
PLATFORM_LABELS = {
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "x": "X",
    "upwork": "Upwork",
    "fiverr": "Fiverr",
    "email": "Email",
    "github": "GitHub",
    "other": "Other",
}


class ApprovalError(Exception):
    """Something that can't be done with an item; the message says why."""


class ApprovalOut(BaseModel):
    id: int
    kind: str
    platform: str
    platform_label: str
    item_type: str
    action_type: str | None
    title: str
    text: str
    original_text: str
    edits: list[dict[str, Any]]
    meta: dict[str, Any]
    status: str
    from_outside: bool
    can_always_allow: bool
    reason: str
    open_url: str
    images: list[dict[str, Any]] = []
    # The platform needs an image (Instagram) and none is attached yet.
    needs_image: bool = False
    conversation_id: int | None
    message_id: int | None
    created_at: datetime
    updated_at: datetime


def _open_url(item: ApprovalItem) -> str:
    source = str(item.meta.get("source_url", ""))
    if source.startswith(("https://", "http://")):
        return source  # e.g. the post you're commenting on
    return OPEN_URLS.get(item.platform, "")


def _needs_image(platform: str, item_type: str) -> bool:
    if item_type != "post":
        return False
    try:
        from junior.playbooks import load_playbooks

        book = load_playbooks().get(platform)
    except Exception:  # a broken playbook is reported at startup, not here
        return False
    return bool(book and book.needs_image)


def to_out(item: ApprovalItem, images: list[dict[str, Any]] | None = None) -> ApprovalOut:
    if images is None:
        from junior.images import images_for

        images = images_for([item.id]).get(item.id, [])
    can_always_allow = False
    if item.kind == "api" and item.status == "waiting" and item.action_type:
        can_always_allow = decide(item.action_type, from_outside=item.from_outside).can_always_allow
    return ApprovalOut(
        id=item.id,
        kind=item.kind,
        platform=item.platform,
        platform_label=PLATFORM_LABELS.get(item.platform, item.platform),
        item_type=item.item_type,
        action_type=item.action_type,
        title=item.title,
        text=item.text,
        original_text=item.original_text,
        edits=item.edits,
        meta=item.meta,
        status=item.status,
        from_outside=item.from_outside,
        can_always_allow=can_always_allow,
        reason=item.reason,
        open_url=_open_url(item),
        images=images,
        needs_image=not images and _needs_image(item.platform, item.item_type),
        conversation_id=item.conversation_id,
        message_id=item.message_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def create_item(
    *,
    kind: Kind,
    platform: str,
    item_type: str,
    text: str,
    title: str = "",
    action_type: str | None = None,
    from_outside: bool = False,
    meta: dict[str, Any] | None = None,
    conversation_id: int | None = None,
) -> ApprovalOut:
    """Put a draft in the queue. API items follow the permission rules; Deny refuses them."""
    text = text.strip()
    if not text:
        raise ApprovalError("The draft is empty.")
    if platform not in PLATFORM_LABELS:
        raise ApprovalError(f"Unknown platform {platform!r}; use one of {sorted(PLATFORM_LABELS)}.")
    status, reason = "waiting", "You send this yourself: copy it, paste it, then mark it as posted."
    if kind == "api":
        if not action_type:
            raise ApprovalError("An API item needs an action type, e.g. linkedin.post.")
        decision = decide(action_type, from_outside=from_outside)
        if decision.rule == "deny":
            audit("action", "approval_refused", result="blocked", detail={"type": action_type, "reason": decision.reason})
            raise ApprovalError(decision.reason)
        reason = decision.reason
        if decision.rule == "auto":
            status = "approved"
    elif action_type:
        raise ApprovalError("Copy-and-paste items have no action type: the system never sends them.")
    with session_scope() as s:
        item = ApprovalItem(
            kind=kind,
            platform=platform,
            item_type=item_type.strip().lower() or "post",
            action_type=action_type,
            title=(title.strip() or text.splitlines()[0])[:200],
            text=text,
            original_text=text,
            edits=[],
            meta=meta or {},
            status=status,
            from_outside=from_outside,
            reason=reason,
            conversation_id=conversation_id,
        )
        s.add(item)
        s.flush()
        out = to_out(item)
    audit(
        "action",
        "approval_created",
        detail={"id": out.id, "kind": kind, "platform": platform, "status": status, "from_outside": from_outside},
        conversation_id=conversation_id,
    )
    return out


def attach_to_message(item_ids: list[int], message_id: int) -> None:
    """Show items made during a turn as cards under that answer."""
    if not item_ids:
        return
    with session_scope() as s:
        for item in s.scalars(select(ApprovalItem).where(ApprovalItem.id.in_(item_ids))):
            item.message_id = message_id


def items_for_messages(message_ids: list[int]) -> dict[int, list[ApprovalOut]]:
    with session_scope() as s:
        rows = s.scalars(
            select(ApprovalItem).where(ApprovalItem.message_id.in_(message_ids)).order_by(ApprovalItem.id)
        ).all()
        from junior.images import images_for

        pictures = images_for([i.id for i in rows])
        found: dict[int, list[ApprovalOut]] = {}
        for item in rows:
            found.setdefault(item.message_id, []).append(to_out(item, pictures.get(item.id, [])))
        return found


def _change(item_id: int, action: str, fn) -> ApprovalOut:
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        if item is None:
            raise LookupError(f"Approval item {item_id} doesn't exist.")
        before = item.status
        fn(item)
        item.updated_at = utcnow()
        s.flush()
        out = to_out(item)
    audit(
        "action",
        f"approval_{action}",
        detail={"id": item_id, "from": before, "to": out.status},
        conversation_id=out.conversation_id,
    )
    return out


def _need(item: ApprovalItem, status: str, kind: str | None = None) -> None:
    if kind and item.kind != kind:
        raise ApprovalError(
            "This is a copy-and-paste item: you send it yourself, then mark it as posted."
            if kind == "api"
            else "This item is sent through the API; approve it instead."
        )
    if item.status != status:
        raise ApprovalError(f"This item is {item.status.replace('_', ' ')}, not {status}.")


def edit_item(item_id: int, text: str) -> ApprovalOut:
    text = text.strip()
    if not text:
        raise ApprovalError("The text can't be empty.")

    def fn(item: ApprovalItem) -> None:
        _need(item, "waiting")
        if text != item.text:
            item.edits = [*item.edits, {"at": utcnow().isoformat(), "before": item.text, "after": text}]
            item.text = text

    return _change(item_id, "edited", fn)


def _need_image_if_required(item: ApprovalItem) -> None:
    from junior.images import images_for

    if _needs_image(item.platform, item.item_type) and not images_for([item.id]).get(item.id):
        raise ApprovalError(f"{PLATFORM_LABELS.get(item.platform, item.platform)} posts need an image: add one first.")


def approve_item(item_id: int, always_allow: bool = False) -> ApprovalOut:
    def fn(item: ApprovalItem) -> None:
        _need(item, "waiting", "api")
        _need_image_if_required(item)
        decision = decide(item.action_type, from_outside=item.from_outside)
        if decision.rule == "deny":
            raise ApprovalError(decision.reason)
        if always_allow:
            if not decision.can_always_allow:
                raise ApprovalError("\"Always allow\" isn't possible for this item (locked, or caused by outside content).")
            set_rule(item.action_type, "auto")
        item.status = "approved"
        item.decided_at = utcnow()
        # The API sender (phase 3) sends exactly this text, once.
        item.meta = {**item.meta, "approved_text": item.text}

    return _change(item_id, "approved", fn)


def mark_posted(item_id: int) -> ApprovalOut:
    def fn(item: ApprovalItem) -> None:
        _need(item, "waiting", "copy")
        _need_image_if_required(item)
        item.status = "posted"
        item.decided_at = item.posted_at = utcnow()

    return _change(item_id, "posted", fn)


def reject_item(item_id: int) -> ApprovalOut:
    def fn(item: ApprovalItem) -> None:
        _need(item, "waiting")
        item.status = "rejected"
        item.decided_at = utcnow()

    return _change(item_id, "rejected", fn)


def restore_item(item_id: int) -> ApprovalOut:
    def fn(item: ApprovalItem) -> None:
        _need(item, "rejected")
        item.status = "waiting"
        item.decided_at = None

    return _change(item_id, "restored", fn)


def recent_titles(days: int = 30, limit: int = 30) -> list[str]:
    """Social drafts made, approved or posted lately, so ideas don't repeat them."""
    from datetime import timedelta

    since = utcnow() - timedelta(days=days)
    with session_scope() as s:
        q = (
            select(ApprovalItem.title, ApprovalItem.platform, ApprovalItem.status)
            .where(
                ApprovalItem.created_at >= since,
                ApprovalItem.platform.in_(("linkedin", "facebook", "instagram", "x")),
                ApprovalItem.status != "rejected",
            )
            .order_by(ApprovalItem.id.desc())
            .limit(limit)
        )
        return [f"{t} ({p}, {st})" for t, p, st in s.execute(q)]


def waiting_count() -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(ApprovalItem).where(ApprovalItem.status == "waiting")) or 0


# ---- API --------------------------------------------------------------------


def _call(fn, *args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ApprovalError as e:
        raise HTTPException(409, str(e)) from None


class NewCopyItem(BaseModel):
    platform: str
    item_type: str = Field(default="post", max_length=40)
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=70000)


class EditBody(BaseModel):
    text: str = Field(min_length=1, max_length=70000)


class ApproveBody(BaseModel):
    always_allow: bool = False


@router.get("/api/approvals", response_model=list[ApprovalOut])
def list_items(status: str = "waiting", platform: str = "", limit: int = 100) -> list[ApprovalOut]:
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, f"status must be 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(ApprovalItem).order_by(ApprovalItem.updated_at.desc()).limit(min(limit, 500))
        if status != "all":
            q = q.where(ApprovalItem.status == status)
        if platform:
            q = q.where(ApprovalItem.platform == platform)
        rows = s.scalars(q).all()
        from junior.images import images_for

        pictures = images_for([i.id for i in rows])
        return [to_out(i, pictures.get(i.id, [])) for i in rows]


@router.get("/api/approvals/count")
def count() -> dict:
    return {"waiting": waiting_count()}


@router.get("/api/approvals/{item_id}", response_model=ApprovalOut)
def get_item(item_id: int) -> ApprovalOut:
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        if item is None:
            raise HTTPException(404, f"Approval item {item_id} doesn't exist.")
        return to_out(item)


@router.post("/api/approvals", response_model=ApprovalOut, status_code=201)
def add_copy_item(body: NewCopyItem) -> ApprovalOut:
    try:
        return create_item(kind="copy", platform=body.platform, item_type=body.item_type, title=body.title, text=body.text)
    except ApprovalError as e:
        raise HTTPException(422, str(e)) from None


@router.patch("/api/approvals/{item_id}", response_model=ApprovalOut)
def patch_item(item_id: int, body: EditBody) -> ApprovalOut:
    return _call(edit_item, item_id, body.text)


@router.post("/api/approvals/{item_id}/approve", response_model=ApprovalOut)
def post_approve(item_id: int, body: ApproveBody | None = None) -> ApprovalOut:
    return _call(approve_item, item_id, bool(body and body.always_allow))


@router.post("/api/approvals/{item_id}/posted", response_model=ApprovalOut)
def post_posted(item_id: int) -> ApprovalOut:
    return _call(mark_posted, item_id)


@router.post("/api/approvals/{item_id}/reject", response_model=ApprovalOut)
def post_reject(item_id: int) -> ApprovalOut:
    return _call(reject_item, item_id)


@router.post("/api/approvals/{item_id}/restore", response_model=ApprovalOut)
def post_restore(item_id: int) -> ApprovalOut:
    return _call(restore_item, item_id)
