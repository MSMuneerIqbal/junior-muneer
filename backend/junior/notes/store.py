"""SQLite is authoritative; notes also have dated Markdown files under data/notes/<folder-id>-<name>/."""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from junior import gate
from junior.audit import audit
from junior.config import get_settings
from junior.db import ClassNote, NotesFolder, ReceivedFile, session_scope
from junior.db.models import utcnow
from junior.files import safe_name

router = APIRouter()
LOCK = RLock()


def markdown(note: ClassNote) -> str:
    sources = "\n".join(f"- {s['filename']} (file {s['id']})" for s in note.sources)
    text = f"# {note.title}\n\nClass date: {note.class_date}\nCourse: {note.subject or 'Not specified'}\n\n"
    text += note.summary + "\n\n" + note.body
    if sources:
        text += "\n\n## Source files\n" + sources
    if note.warnings:
        text += "\n\n## Reading limitations\n" + "\n".join(f"- {w}" for w in note.warnings)
    return text.rstrip() + "\n"


def _storage_path(note: ClassNote, folder_name: str) -> Path:
    root = get_settings().data_path / "notes"
    folder = root / f"{note.folder_id}-{safe_name(folder_name)[:60]}"
    if root.is_symlink() or folder.is_symlink():
        raise ValueError("The notes storage folder cannot be a link.")
    filename = f"{note.class_date} {note.id}-{safe_name(note.title)[:90]}.md"
    return folder / filename


def _mirror(note: ClassNote, folder_name: str) -> Path:
    path = _storage_path(note, folder_name)
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("The note's storage file cannot be a link.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=folder, encoding="utf-8", newline="\n", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(markdown(note))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        return path
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def out(note: ClassNote, *, full: bool = True) -> dict:
    data = {"id": note.id, "title": note.title, "subject": note.subject, "class_date": note.class_date,
            "folder_id": note.folder_id, "folder_name": note.folder.name,
            "summary": note.summary, "archived": note.archived, "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(), "sources": note.sources, "warnings": note.warnings,
            "conversation_id": note.conversation_id, "body": note.body}
    data["revision"] = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if not full:
        data.pop("body")
    return data


def _folder(s, name: str) -> NotesFolder:
    name = " ".join(name.split())
    if not name or len(name) > 80 or re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or name in (".", ".."):
        raise HTTPException(422, "Use a folder name of 1–80 characters inside Notes, without a filesystem path or special path characters.")
    key = name.casefold()
    folder = s.scalar(select(NotesFolder).where(NotesFolder.name_key == key))
    if folder is None:
        folder = NotesFolder(name=name, name_key=key)
        s.add(folder)
        s.flush()
    return folder


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/api/note-folders", status_code=201)
def create_folder(body: FolderCreate):
    with LOCK, session_scope() as s:
        folder = _folder(s, body.name)
        result = {"id": folder.id, "name": folder.name}
    audit("action", "notes_folder_ready", detail={"folder_id": result["id"]})
    return result


@router.get("/api/note-folders")
def folders():
    with session_scope() as s:
        counts = dict(s.execute(select(ClassNote.folder_id, func.count(ClassNote.id)).where(ClassNote.archived.is_(False))
                                .group_by(ClassNote.folder_id)).all())
        files = dict(s.execute(select(ReceivedFile.library_folder_id, func.count(ReceivedFile.id)).where(ReceivedFile.library_archived.is_(False)).group_by(ReceivedFile.library_folder_id)).all())
        return [{"id": f.id, "name": f.name, "note_count": counts.get(f.id, 0), "file_count": files.get(f.id, 0)}
                for f in s.scalars(select(NotesFolder).order_by(NotesFolder.name))]


def save_note(*, title, subject, class_date, summary, body, source_text, sources, warnings, context, folder_name="Class notes"):
    context.check_task_limits()
    with LOCK, session_scope() as s:
        if context.task_id:
            existing = s.scalar(select(ClassNote).where(ClassNote.task_id == context.task_id))
            if existing:
                return out(existing)
        folder = _folder(s, folder_name)
        note = ClassNote(title=title, folder=folder, subject=subject, class_date=class_date, summary=summary, body=body,
                         source_text=source_text, sources=sources, warnings=warnings,
                         conversation_id=context.conversation_id, task_id=context.task_id)
        s.add(note)
        s.flush()
        _mirror(note, folder.name)
        result = out(note)
    audit("action", "class_notes_saved", detail={"note_id": result["id"], "sources": len(sources)},
          conversation_id=context.conversation_id)
    return result


def _get(s, note_id):
    note = s.get(ClassNote, note_id)
    if note is None:
        raise HTTPException(404, "These notes were not found.")
    return note


@router.get("/api/notes")
def list_notes(q: str = "", class_date: str = "", archived: bool = False, limit: int = 100, folder_id: int | None = None) -> list[dict]:
    with session_scope() as s:
        query = select(ClassNote).where(ClassNote.archived == archived)
        if q.strip():
            word = "%" + q.strip()[:200].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(or_(*(field.ilike(word, escape="\\") for field in
                                      (ClassNote.title, ClassNote.subject, ClassNote.body))))
        if class_date:
            query = query.where(ClassNote.class_date == class_date)
        if folder_id is not None:
            query = query.where(ClassNote.folder_id == folder_id)
        return [out(n, full=False) for n in s.scalars(query.order_by(ClassNote.class_date.desc(), ClassNote.id.desc())
                                                   .limit(max(1, min(limit, 200))))]


@router.get("/api/notes/{note_id}")
def get_note(note_id: int):
    with session_scope() as s:
        return out(_get(s, note_id))


class NoteEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=64, max_length=64)
    folder_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(max_length=120)
    class_date: date
    summary: str = Field(max_length=1200)
    body: str = Field(min_length=1, max_length=60000)


@router.put("/api/notes/{note_id}")
def edit_note(note_id: int, body: NoteEdit):
    if not body.title.strip() or not body.body.strip():
        raise HTTPException(422, "A title and note text are required.")
    with LOCK, session_scope() as s:
        note = _get(s, note_id)
        if out(note)["revision"] != body.revision:
            raise HTTPException(409, "These notes changed. Reopen them before saving your edit.")
        old_folder = s.get(NotesFolder, note.folder_id)
        old_path = _storage_path(note, old_folder.name)
        folder = s.get(NotesFolder, body.folder_id)
        if folder is None:
            raise HTTPException(422, "Choose an existing Notes folder, or create it first.")
        for name in ("title", "subject", "summary", "body"):
            setattr(note, name, getattr(body, name).strip())
        note.class_date, note.updated_at = body.class_date.isoformat(), utcnow()
        note.folder_id = folder.id
        note.folder = folder
        new_path = _mirror(note, folder.name)
        if new_path != old_path and old_path.is_file() and not old_path.is_symlink():
            old_path.unlink()
        result = out(note)
    audit("action", "class_notes_edited", detail={"note_id": note_id})
    return result


class ArchiveEdit(BaseModel):
    archived: bool
    revision: str = Field(min_length=64, max_length=64)


@router.post("/api/notes/{note_id}/archive")
def archive_note(note_id: int, body: ArchiveEdit):
    with LOCK, session_scope() as s:
        note = _get(s, note_id)
        if out(note)["revision"] != body.revision:
            raise HTTPException(409, "These notes changed. Reopen them before archiving or restoring.")
        note.archived, note.updated_at = body.archived, utcnow()
        result = out(note)
    audit("action", "class_notes_archived" if body.archived else "class_notes_restored", detail={"note_id": note_id})
    return result


@router.get("/api/notes/{note_id}/download")
def download_note(note_id: int):
    with session_scope() as s:
        note = _get(s, note_id)
        filename = f"{note.class_date} {safe_name(note.title)[:110]}.md"
        from urllib.parse import quote
        return Response(markdown(note), media_type="text/markdown; charset=utf-8", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename), "X-Content-Type-Options": "nosniff"})


def find_notes_for(context, query: str = "", class_date: str = "", folder_name: str = "") -> str:
    folder_id = None
    if folder_name:
        with session_scope() as s:
            folder = s.scalar(select(NotesFolder).where(NotesFolder.name_key == " ".join(folder_name.split()).casefold()))
            if folder is None:
                return "No folder with that name in Notes."
            folder_id = folder.id
    rows = list_notes(query, class_date, False, 20, folder_id)
    text = "\n".join(f"Note {r['id']}: {r['title']} — {r['class_date']} — {r['subject']} — folder {r['folder_name']}\n{r['summary']}" for r in rows)
    return gate.fence(context, text or "No matching saved notes.", "saved class-notes search results")


def read_note_for(context, note_id: int) -> str:
    from junior.intents import reading_refusal
    if why := reading_refusal(context):
        return why
    with session_scope() as s:
        note = _get(s, note_id)
        return gate.fence(context, markdown(note), f"saved class notes {note.id}")
