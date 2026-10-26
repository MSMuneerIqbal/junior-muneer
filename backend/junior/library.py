"""A file gallery over stored originals. Uploading/indexing never parses files or calls AI."""
import hashlib
import json
from pathlib import Path

from agents import RunContextWrapper, function_tool
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select

from junior import gate
from junior.agent.context import TurnContext
from junior.db import NotesFolder, ReceivedFile, session_scope
from junior.files import files_dir, safe_name
from junior.notes.store import LOCK, _folder

router = APIRouter()


def output(row, folder):
    from junior.settings_store import get_setting
    from junior.timeutil import zone
    data = {"id": row.id, "filename": row.filename, "mime": row.mime, "size": row.size,
        "folder_id": row.library_folder_id, "folder_name": folder.name, "archived": row.library_archived,
        "drive_link": row.drive_link, "created_at": row.created_at.astimezone(zone(get_setting("timezone"))).isoformat(), "local": bool(row.stored_as)}
    data["revision"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data


def _get(s, number):
    row = s.get(ReceivedFile, number)
    if row is None or row.library_folder_id is None:
        raise HTTPException(404, "Saved file not found.")
    return row, s.get(NotesFolder, row.library_folder_id)


def _path(row):
    root = files_dir().resolve()
    path = root / row.stored_as
    if not row.stored_as or path.is_symlink() or path.resolve().parent != root or not path.is_file():
        raise HTTPException(404, "The original file is missing.")
    return path


@router.get("/api/library/files")
def list_files(q: str = "", folder_id: int | None = None, archived: bool = False, class_date: str = "", limit: int = 200):
    query = select(ReceivedFile, NotesFolder).join(NotesFolder, NotesFolder.id == ReceivedFile.library_folder_id)
    query = query.where(ReceivedFile.library_archived == archived)
    if folder_id is not None:
        query = query.where(ReceivedFile.library_folder_id == folder_id)
    if class_date:
        from datetime import date, datetime, timedelta, UTC
        from junior.settings_store import get_setting
        from junior.timeutil import zone
        try:
            start = datetime.combine(date.fromisoformat(class_date), datetime.min.time(), zone(get_setting("timezone"))).astimezone(UTC)
        except ValueError:
            raise HTTPException(422, "Use YYYY-MM-DD for the date.") from None
        query = query.where(ReceivedFile.created_at >= start, ReceivedFile.created_at < start + timedelta(days=1))
    if q.strip():
        word = "%" + q.strip()[:200].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(ReceivedFile.filename.ilike(word, escape="\\"))
    with session_scope() as s:
        rows = [output(row, folder) for row, folder in s.execute(query.order_by(ReceivedFile.created_at.desc(), ReceivedFile.id.desc()).limit(max(1, min(limit, 1000))))]
    return rows


class FileEdit(BaseModel):
    folder_id: int = Field(ge=1)
    filename: str = Field(min_length=1, max_length=200)
    revision: str
    archived: bool = False


class FileRemoval(BaseModel):
    revision: str = Field(min_length=64, max_length=64)


@router.delete("/api/library/files/{number}")
def delete_file(number: int, body: FileRemoval):
    from junior.audit import audit
    from junior.computer.sender import to_recycle_bin
    from junior.db import ApprovalItem, BackgroundTask
    import re
    with LOCK, session_scope() as s:
        row, folder = _get(s, number)
        if output(row, folder)["revision"] != body.revision:
            raise HTTPException(409, "This file changed. Reopen its menu before deleting it.")
        for task in s.scalars(select(BackgroundTask).where(BackgroundTask.status == "running")):
            if number in task.file_ids or re.search(rf"\[file {number}:", task.request):
                raise HTTPException(409, "A running task uses this file. Stop it or wait for it to finish before deleting.")
        pending = []
        for item in s.scalars(select(ApprovalItem).where(ApprovalItem.status.in_(("waiting", "approved", "check_manually")))):
            if number in (item.meta.get("snapshot_id"), item.meta.get("source_file_id")):
                if item.meta.get("sending_at") or item.status == "check_manually":
                    raise HTTPException(409, "An action is sending or awaiting a manual check for this file. Resolve it before deleting.")
                pending.append(item)
        if row.stored_as:
            root = files_dir().resolve()
            path = root / row.stored_as
            if path.is_symlink() or path.resolve().parent != root:
                raise HTTPException(409, "This stored path is not a normal Junior file.")
            if path.exists():
                try:
                    to_recycle_bin(path)
                except OSError:
                    raise HTTPException(409, "Couldn't confirm moving this copy to the Recycle Bin. Reopen the file before trying again.") from None
        for item in pending:
            item.status, item.reason = "rejected", "The source file was deleted from Junior."
        s.delete(row)
    audit("action", "library_file_deleted", detail={"file_id": number})
    return {"deleted_id": number}


@router.put("/api/library/files/{number}")
def edit_file(number: int, body: FileEdit):
    with LOCK, session_scope() as s:
        row, folder = _get(s, number)
        if output(row, folder)["revision"] != body.revision:
            raise HTTPException(409, "The file changed. Reopen it before editing.")
        if s.get(NotesFolder, body.folder_id) is None:
            raise HTTPException(422, "Choose an existing folder.")
        row.filename, row.library_folder_id, row.library_archived = safe_name(body.filename), body.folder_id, body.archived
        return output(row, s.get(NotesFolder, body.folder_id))


@router.get("/api/library/files/{number}")
def get_file(number: int):
    with session_scope() as s:
        return output(*_get(s, number))


@router.get("/api/library/files/{number}/download")
def download(number: int):
    with session_scope() as s:
        row, _ = _get(s, number)
        if not row.stored_as:
            return RedirectResponse(row.drive_link, status_code=303)
        return FileResponse(_path(row), filename=row.filename, media_type=row.mime, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/api/library/files/{number}/inline")
def inline(number: int):
    with session_scope() as s:
        row, _ = _get(s, number)
        if row.mime not in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"):
            raise HTTPException(415, "Download this file to open it.")
        return FileResponse(_path(row), media_type=row.mime, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.get("/api/library/files/{number}/preview")
def preview(number: int):
    from junior.reading import ReadError, extract_text
    with session_scope() as s:
        row, _ = _get(s, number)
        try:
            text = extract_text(_path(row).read_bytes(), row.mime, row.filename, max_chars=15000)
        except ReadError as e:
            return {"text": "", "message": str(e)}
        return {"text": text, "message": ""}


def file_in_folder(number, folder_name, new_name=""):
    with LOCK, session_scope() as s:
        row = s.get(ReceivedFile, number)
        if row is None:
            raise ValueError("Source file not found.")
        folder = _folder(s, folder_name or "Uploads")
        row.library_folder_id, row.library_archived = folder.id, False
        if new_name:
            row.filename = safe_name(new_name)
        return output(row, folder)


def register_cloud_file(title, mime, link, conversation_id=None):
    with LOCK, session_scope() as s:
        found = s.scalar(select(ReceivedFile).where(ReceivedFile.drive_link == link, ReceivedFile.source == "drive"))
        if found:
            return found.id
        folder = _folder(s, "Documents")
        row = ReceivedFile(conversation_id=conversation_id, source="drive", filename=safe_name(title), mime=mime,
                           stored_as="", size=0, drive_link=link, library_folder_id=folder.id)
        s.add(row); s.flush()
        return row.id


class DriveSave(BaseModel):
    folder: str = Field(default="", max_length=500)
    access: Literal["", "private", "reader", "writer"] = ""


@router.post("/api/library/files/{number}/drive")
async def save_or_share_on_drive(number: int, body: DriveSave, request: Request):
    from junior.approvals import ApprovalError, create_item
    from junior.google.drive import file_id
    from junior.google.sharing import sharing_label, sharing_meta
    from junior.settings_store import all_settings
    from junior.transfers.sources import source_file, snapshot
    from junior.senders.dispatch import send_item, SendError
    from junior.google.auth import GoogleError
    from junior.permissions import plan_mode_refusal
    if why := plan_mode_refusal():
        raise HTTPException(409, why)
    with session_scope() as s:
        row, _ = _get(s, number)
        name, link = row.filename, row.drive_link
    share = sharing_meta(body.access)
    try:
        if link and not body.folder:
            if share["sharing_role"] == "private":
                raise HTTPException(422, "Choose public viewing or editing to share an existing file.")
            action = "google.drive.share"
            description = f"{sharing_label(share['sharing_role'])}.\n{name}\n{link}"
            meta = {"op": "share_existing", "drive_file_id": file_id(link), "source_url": link, "sharing_role": share["sharing_role"]}
        else:
            context = TurnContext(conversation_id=None, settings=all_settings())
            filename, data, mime = await source_file(context, file_number=number)
            meta = {"op": "place_document", "folder": body.folder, "source_file_id": number, **share, **snapshot(context, filename, data, mime)}
            action = "google.drive.save"
            description = f"Save {filename} in Google Drive folder {body.folder or 'My Drive'}.\n{sharing_label(share['sharing_role'])}."
        item = create_item(kind="api", platform="google", item_type="file_transfer", action_type=action, title=f"Drive: {name}", text=description, meta=meta)
        if item.status == "approved":
            item = await send_item(item.id, request.app.state.senders)
        return item
    except (ApprovalError, SendError, ValueError, GoogleError) as e:
        raise HTTPException(409, str(e)) from None


@function_tool
def find_saved_files(ctx: RunContextWrapper[TurnContext], query: str = "", folder_name: str = "") -> str:
    """Find saved original files in the Notes file gallery by filename/folder, without reading their contents."""
    folder_id = None
    if folder_name:
        with session_scope() as s:
            folder = s.scalar(select(NotesFolder).where(NotesFolder.name_key == " ".join(folder_name.split()).casefold()))
            if folder is None:
                return "No saved folder with that name."
            folder_id = folder.id
    return gate.fence(ctx.context, json.dumps(list_files(query, folder_id), ensure_ascii=False), "saved-file names and locations (not file contents)")


def save_text_to_library_for(context, title, text, your_words, folder_name="Notes", markdown=False):
    """Save the user's original text as TXT (or MD) in the file gallery, without rewriting, summarizing or research.
    text must be copied exactly from their own messages or current Paste box; title/folder come from their request.
    """
    from junior.permissions import plan_mode_refusal
    from junior.files import save_received
    if why := plan_mode_refusal():
        return why
    if not gate.you_said(context, your_words):
        return "NOT saved: quote the user's own saving request."
    from junior.db import Message
    with session_scope() as s:
        originals = s.scalars(select(Message.content).where(Message.id.in_(context.user_message_ids), Message.source == "user")).all()
    originals.append((context.paste or {}).get("text", ""))
    if not text.strip() or not any(text in original for original in originals):
        return "NOT saved: use their exact text, without rewriting it."
    if not text.strip():
        return "NOT saved: the text is empty."
    name = safe_name(title)
    extension = ".md" if markdown else ".txt"
    if not name.lower().endswith(extension):
        name += extension
    number, _ = save_received(text.encode("utf-8"), name, "text/markdown" if markdown else "text/plain", "library", context.conversation_id, library_folder=folder_name)
    return f"Saved {name} in {folder_name}, without changing the text. [Open saved file](/notes?file={number})"


@function_tool
def save_text_to_library(ctx: RunContextWrapper[TurnContext], title: str, text: str, your_words: str,
                         folder_name: str = "Notes", markdown: bool = False) -> str:
    """Save text copied exactly from the user's messages or current Paste box as TXT/MD, without rewriting."""
    return save_text_to_library_for(ctx.context, title, text, your_words, folder_name, markdown)
