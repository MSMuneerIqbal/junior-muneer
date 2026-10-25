"""Explicit Google-file requests become approval cards; local downloads remain available."""
import json

from junior import gate
from junior.approvals import ApprovalError, create_item
from junior.documents.export import markdown
from junior.google.tools import _not_ready


def queue_workspace(context, doc, sources, output_format):
    context.check_task_limits()
    if not gate.you_said(context, context.user_text):
        return "Google creation was not queued: I couldn't verify the original request. Your local file is ready."
    if refusal := _not_ready("drive.file"):
        return refusal + " Your local file is ready above."
    action = "google.docs.create" if output_format == "google_doc" else "google.sheets.create"
    content = markdown(doc, sources) if output_format == "google_doc" else json.dumps(
        {"title": doc.title, "headers": doc.headers, "rows": doc.rows}, ensure_ascii=False, indent=2)
    try:
        from junior.google.sharing import sharing_meta
        item = create_item(kind="api", platform="google", item_type="document" if output_format == "google_doc" else "spreadsheet",
                           action_type=action, title=doc.title, text=content, from_outside=True,
                           conversation_id=context.conversation_id, meta=sharing_meta(request=context.user_text))
    except ApprovalError as e:
        return f"Google creation was refused: {e}. Your local file is ready above."
    context.approval_ids.append(item.id)
    return f"Google creation is waiting for your approval (item {item.id}). Approve the card to create it in Drive."
