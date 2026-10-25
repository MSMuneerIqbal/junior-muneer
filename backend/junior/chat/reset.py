"""Exact session commands are handled locally, before model/key/budget checks."""
from sqlalchemy import select

from junior.audit import audit
from junior.db import ApprovalItem, BackgroundTask, Conversation, session_scope
from junior.db.models import utcnow

COMMANDS = {"/clear", "cls"}


def reset_session(conversation_id):
    with session_scope() as s:
        old = s.get(Conversation, conversation_id) if conversation_id else None
        kind = old.kind if old and old.kind in ("text", "voice", "whatsapp") else "text"
        if old:
            for task in s.scalars(select(BackgroundTask).where(BackgroundTask.conversation_id == old.id, BackgroundTask.status == "running")):
                task.status, task.stage, task.updated_at = "cancelled", "Session cleared", utcnow()
            for item in s.scalars(select(ApprovalItem).where(ApprovalItem.conversation_id == old.id, ApprovalItem.status.in_(("waiting", "approved")))):
                if not item.meta.get("sending_at"):
                    item.status, item.reason, item.updated_at = "rejected", "The originating session was cleared.", utcnow()
            s.delete(old)
            s.flush()
        # Allocate a distinct ID even when SQLite would reuse the deleted maximum row ID.
        from sqlalchemy import func
        next_id = max(conversation_id or 0, s.scalar(select(func.max(Conversation.id))) or 0) + 1
        new = Conversation(id=next_id, kind=kind, title="WhatsApp · New session" if kind == "whatsapp" else "New chat")
        s.add(new); s.flush()
        result = {"id": new.id, "title": new.title}
    audit("action", "session_cleared", detail={"previous_id": conversation_id, "new_id": result["id"]})
    return result
