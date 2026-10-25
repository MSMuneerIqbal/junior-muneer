"""Small deterministic tools for file placement and ZIP delivery; all writes use normal approval cards."""
from pathlib import Path
from typing import Literal

from agents import RunContextWrapper, function_tool

from junior import gate
from junior.agent.context import TurnContext
from junior.computer.paths import PathRefused, check
from junior.google.auth import GoogleError
from junior.permissions import decide, plan_mode_refusal
from junior.transfers.sources import snapshot, source_file


def refusal(context, words, actions):
    if why := plan_mode_refusal():
        return why
    if not gate.you_said(context, words):
        return "NOT done: quote the user's own request for this transfer exactly."
    for action in actions:
        decision = decide(action, from_outside=context.outside_content_seen)
        if decision.rule == "deny" or decision.held:
            return "NOT done: " + decision.reason
    return None


async def queue(context, action, platform, text, title, meta):
    from junior.approvals import ApprovalError, create_item
    from junior.senders.dispatch import SendError, send_item
    from junior.senders.registry import CURRENT
    if context.actions_done >= gate.MAX_ACTIONS_PER_TURN:
        return "NOT done: the action limit for this message was reached."
    try:
        item = create_item(kind="api", platform=platform, item_type="file_transfer", action_type=action,
            text=text, title=title, meta=meta, from_outside=context.outside_content_seen, conversation_id=context.conversation_id)
    except ApprovalError as e:
        return f"NOT done: {e}"
    context.actions_done += 1
    context.approval_ids.append(item.id)
    if item.status == "approved":
        try:
            item = await send_item(item.id, CURRENT)
        except SendError as e:
            return f"NOT done: {e}"
    context.emit({"type": "approval", "item": item.model_dump(mode="json")})
    if item.status == "posted":
        return "Done: " + item.meta.get("result", "") + ("\n" + item.meta["post_url"] if item.meta.get("post_url") else "")
    if item.status == "waiting":
        return f"Prepared on approval card {item.id}. Waiting for Approve; the destination has not been changed or sent yet."
    return f"Not confirmed: {item.meta.get('last_error', '')}. Check the card; never claim it succeeded."


async def place_document_for(context, destination, your_words, destination_kind="pc", file_number=0,
                             pc_file="", drive_link="", note_id=0, new_name="", share_role=""):
    action = "computer.write" if destination_kind == "pc" else "google.drive.save"
    if destination_kind not in ("pc", "google_drive", "notes"):
        return "NOT done: destination_kind must be pc, google_drive or notes."
    from junior.google.sharing import sharing_meta, sharing_label
    share = sharing_meta(share_role, your_words) if destination_kind == "google_drive" else {}
    actions = [] if destination_kind == "notes" else [action] + share.get("required_actions", [])
    if why := refusal(context, your_words, actions):
        return why
    try:
        if destination_kind == "google_drive":
            from junior.google import auth
            if not auth.is_connected() or not auth.has_scope("drive.file"):
                return "NOT done: connect Google with file creation allowed in Settings → Connections."
        name, data, mime = await source_file(context, file_number, pc_file, drive_link, note_id)
        from junior.transfers.archives import blocked_name
        if blocked_name(name):
            return "NOT done: that filename identifies a secret file, so it cannot be transferred."
        if new_name:
            from junior.files import safe_name
            original = name
            name = safe_name(new_name)
            if not Path(name).suffix:
                name += Path(original).suffix
            if blocked_name(name):
                return "NOT done: choose a normal document filename, not a blocked secret filename."
        if destination_kind == "notes":
            from junior.files import save_received
            from junior.library import file_in_folder
            number = file_number
            if not number:
                number, _ = save_received(data, name, mime, "library", context.conversation_id, library_folder=destination or "Uploads")
            saved = file_in_folder(number, destination, name)
            return f"Saved the original file {saved['filename']} in Notes folder {saved['folder_name']} without reading its contents. [Open saved file](/notes?file={number})"
        if destination_kind == "pc":
            folder = check(destination, context)
            if folder.exists() and not folder.is_dir():
                return "NOT done: destination must be a folder. Give the folder path and optional new_name separately."
            path = check(str(folder / name), context)
            if path.exists():
                return f"NOT done: {path} already exists. Choose a different filename; existing files are never overwritten."
            meta = {"op": "copy_document", "path": str(path)}
            platform, description = "computer", f"Copy the actual file {name} to {path}. Create missing folders. Keep the source."
        else:
            if len(data) > 20 * 1024 * 1024:
                return "NOT done: Google Drive transfers support files up to 20 MB."
            meta = {"op": "place_document", "folder": destination, "source_file_id": file_number, **share}
            platform, description = "google", f"Save a new copy of {name} to Google Drive folder {destination or 'My Drive'}. Create missing folders. Keep the source."
            description += "\n" + sharing_label(share["sharing_role"]) + "."
        meta.update(snapshot(context, name, data, mime))
        description += f"\nSize: {len(data):,} bytes. The prepared file can be downloaded for review."
        return await queue(context, action, platform, description, f"Place {name}", meta)
    except (ValueError, OSError, PathRefused, GoogleError) as e:
        return f"NOT done: {e}"


async def zip_folder_for(context, folder, your_words, source_kind="pc", send_whatsapp=True, archive_name=""):
    actions = ["files.archive_whatsapp", "google.drive.save", "whatsapp.to_self"] if send_whatsapp else []
    if why := refusal(context, your_words, actions):
        return why
    if source_kind not in ("pc", "google_drive"):
        return "NOT done: source_kind must be pc or google_drive."
    try:
        from junior.transfers.archives import cloud_zip, local_zip
        context.emit({"type": "step", "id": "zip-prepare", "kind": "team", "label": "Checking and zipping the folder", "status": "running"})
        name, data, entries = await (local_zip(context, folder) if source_kind == "pc" else cloud_zip(folder))
        if archive_name:
            from junior.files import safe_name
            name = safe_name(archive_name)
            if not name.lower().endswith(".zip"):
                name += ".zip"
        meta = snapshot(context, name, data, "application/zip")
        from junior.library import file_in_folder
        file_in_folder(meta["snapshot_id"], "Archives")
        context.emit({"type": "step", "id": "zip-prepare", "kind": "team", "label": f"ZIP ready: {len(entries)} entries", "status": "done"})
        download = f"[Download ZIP](/api/files/{meta['snapshot_id']}/download)"
        if not send_whatsapp:
            return f"Created {name} ({len(data):,} bytes; {len(entries)} entries). {download}"
        from junior.google import auth
        from junior.whatsapp import configured
        if not configured() or not auth.is_connected() or not auth.has_scope("drive.file"):
            return f"ZIP ready: {download}. NOT sent: connect WhatsApp and Google in Settings → Connections. ZIP delivery uses a private Drive download link because Meta rejects ZIP attachments."
        meta.update(entry_count=len(entries), source_folder=folder, required_actions=["google.drive.save", "whatsapp.to_self"])
        description = (f"Send ZIP {name} from {source_kind} folder {folder} to your own WhatsApp.\n"
            f"{len(entries)} entries; {len(data):,} bytes.\n"
            "Upload the prepared ZIP privately to My Drive in your connected Google account, then send its link. "
            "No public sharing permission is created. WhatsApp's API rejects direct ZIP attachments.")
        answer = await queue(context, "files.archive_whatsapp", "whatsapp", description, f"Send ZIP {name}", meta)
        return answer + "\n" + download
    except (ValueError, OSError, PathRefused, GoogleError, TimeoutError) as e:
        context.emit({"type": "step", "id": "zip-prepare", "kind": "team", "label": "ZIP preparation stopped", "status": "done"})
        return f"NOT done: {e}"


@function_tool
async def place_document(ctx: RunContextWrapper[TurnContext], destination: str, your_words: str,
                         destination_kind: Literal["pc", "google_drive", "notes"] = "pc", file_number: int = 0,
                         pc_file: str = "", drive_link: str = "", note_id: int = 0, new_name: str = "",
                         share_role: Literal["", "private", "reader", "writer"] = "") -> str:
    """Copy the ACTUAL document into a specified folder/drive. PDF/DOCX/PPTX/images/binaries retain their bytes.
    Select exactly one source: file_number from an uploaded/generated [file N] tag, pc_file path, drive_link, or note_id.
    destination is a full local folder path for pc, an exact Google Drive folder path/link, or a Notes-library folder name for notes.
    Missing folders are created as part of the permitted action. Never overwrites. new_name optional; keeps source extension.
    your_words is the user's exact transfer request. Changes follow approval rules; report waiting until confirmed.
    share_role for Google Drive: empty uses their saved setting; reader = public view, writer = public edit, private = private.
    """
    return await place_document_for(ctx.context, destination, your_words, destination_kind, file_number, pc_file, drive_link, note_id, new_name, share_role)


async def share_drive_file_for(context, file_link, your_words, access="reader"):
    if why := refusal(context, your_words, ["google.drive.share"]):
        return why
    from junior.google.drive import file_id
    from junior.google.sharing import sharing_label
    try:
        fid = file_id(file_link)
    except GoogleError as e:
        return str(e)
    return await queue(context, "google.drive.share", "google", f"{sharing_label(access)}.\n{file_link}",
                       "Share Drive file", {"op": "share_existing", "drive_file_id": fid, "sharing_role": access, "source_url": file_link})


@function_tool
async def share_drive_file(ctx: RunContextWrapper[TurnContext], file_link: str, your_words: str,
                           access: Literal["reader", "writer"] = "reader") -> str:
    """Make an existing Google Drive file public by link: reader=view, writer=edit. Exact own user request required.
    Follows google.drive.share permission; the card states who can view/edit. Never grants ownership.
    """
    return await share_drive_file_for(ctx.context, file_link, your_words, access)


@function_tool
async def zip_folder(ctx: RunContextWrapper[TurnContext], folder: str, your_words: str,
                     source_kind: Literal["pc", "google_drive"] = "pc", send_whatsapp: bool = True, archive_name: str = "") -> str:
    """Package a real folder recursively as ZIP, optionally send a private Drive download link to the owner's WhatsApp.
    folder is an actual PC path or exact Google Drive path/folder link. Preserve subfolders and source files.
    The official WhatsApp API rejects ZIP attachments; use the approved private-link delivery, never disguise the file.
    send_whatsapp=false makes a downloadable ZIP only. Limit 500 entries, 100 MB input, 20 MB ZIP and two minutes.
    Refuses secrets, shortcuts/links and ambiguous or changing folders instead of silently omitting content.
    your_words must quote the user's request exactly. Delivery waits for the configured approval rules.
    """
    return await zip_folder_for(ctx.context, folder, your_words, source_kind, send_whatsapp, archive_name)


from junior.library import find_saved_files, save_text_to_library
TRANSFER_TOOLS = [place_document, zip_folder, find_saved_files, save_text_to_library, share_drive_file]
