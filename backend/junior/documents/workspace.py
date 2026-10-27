"""Explicit Google-file requests become approval cards; local downloads remain available."""
import json

from junior import gate
from junior.approvals import ApprovalError, create_item
from junior.documents.export import markdown
from junior.google.tools import _not_ready


def queue_workspace(context, doc, sources, output_format, slide_count=10):
    from junior.permissions import plan_mode_refusal
    if refusal := plan_mode_refusal():
        return refusal
    context.check_task_limits()
    if not gate.you_said(context, context.user_text):
        return "Google creation was not queued: I couldn't verify the original request. Your local file is ready."
    if refusal := _not_ready("drive.file"):
        return refusal + " Your local file is ready above."
    action = {"google_doc": "google.docs.create", "google_sheet": "google.sheets.create", "google_slides": "google.slides.create"}[output_format]
    content = markdown(doc, sources) if output_format == "google_doc" else json.dumps(
        {"title": doc.title, "headers": doc.headers, "rows": doc.rows}, ensure_ascii=False, indent=2)
    if output_format == "google_slides":
        used = {i for slide in doc.slides for i in slide.source_ids}
        content = json.dumps({"document": doc.model_dump(), "sources": [s for s in sources if s["id"] in used],
                              "slide_count": slide_count}, ensure_ascii=False, indent=2)
        if len(content) > 120000:
            return "Google creation was not queued: the presentation exceeds the review limit. Your local file is ready; request shorter notes or fewer slides."
    try:
        from junior.google.sharing import sharing_meta
        item = create_item(kind="api", platform="google", item_type={"google_doc": "document", "google_sheet": "spreadsheet", "google_slides": "presentation"}[output_format],
                           action_type=action, title=doc.title, text=content, from_outside=True,
                           conversation_id=context.conversation_id, meta=sharing_meta(request=context.user_text))
    except ApprovalError as e:
        return f"Google creation was refused: {e}. Your local file is ready above."
    context.approval_ids.append(item.id)
    return f"Google creation is waiting for your approval (item {item.id}). Approve the card to create it in Drive."
