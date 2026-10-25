"""Files you send Junior Muneer: on WhatsApp (documents, photos) or with 📎 in the chat.

Each is kept in data/files under a random name and gets a number. Your message carries a tag like
"[file 3: CV.pdf (PDF, 52 KB)]" so Junior knows it's there; he then does what you ask with it (save it to
your Google Drive). Only the file's name and type reach the AI, never its contents.

    POST /api/files   upload a file from the chat (returns its number and tag)
"""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from junior.config import get_settings
from junior.db import ReceivedFile, session_scope

router = APIRouter()
MAX_BYTES = 25 * 1024 * 1024
TAG = re.compile(r"\[file (\d+):")


def files_dir() -> Path:
    path = get_settings().data_path / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(filename: str) -> str:
    name = " ".join(re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", filename or "").split()).strip(" .")
    return name[:150] or "file"


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, round(n / 1024))} KB"


def _kind(mime: str, name: str) -> str:
    if name.lower().endswith(".pptx"):
        return "PowerPoint"
    if mime == "application/pdf":
        return "PDF"
    if mime.startswith("image/"):
        return "photo"
    if "word" in mime or name.lower().endswith((".doc", ".docx")):
        return "Word file"
    if "sheet" in mime or "excel" in mime or name.lower().endswith((".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    return mime.rsplit("/", 1)[-1] or "file"


def tag(row: ReceivedFile) -> str:
    return f"[file {row.id}: {row.filename} ({_kind(row.mime, row.filename)}, {_size(row.size)})]"


def save_received(data: bytes, filename: str, mime: str, source: str, conversation_id: int | None = None,
                  *, index_in_library: bool = True, library_folder: str = "") -> tuple[int, str]:
    """Keep a file you sent. Returns (its number, its tag for your message)."""
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"The file is too big (over {MAX_BYTES // 1024 // 1024} MB).")
    name = safe_name(filename)
    ending = Path(name).suffix.lower()[:10]
    stored = f"{uuid.uuid4().hex}{ending if re.fullmatch(r'\.[a-z0-9]{1,9}', ending) else ''}"
    (files_dir() / stored).write_bytes(data)
    from junior.notes.store import LOCK
    with LOCK, session_scope() as s:
        folder_id = None
        if index_in_library:
            from junior.notes.store import _folder
            folder_id = _folder(s, library_folder or ("Documents" if source == "generated" else "Uploads")).id
        row = ReceivedFile(conversation_id=conversation_id, source=source, filename=name,
                           library_folder_id=folder_id,
                           mime=(mime or "application/octet-stream")[:120], size=len(data), stored_as=stored, drive_link="")
        s.add(row)
        s.flush()
        return row.id, tag(row)


def received(file_id: int) -> tuple[ReceivedFile, bytes] | None:
    """A file you sent, with its content (None if there's no such file, or it's gone from the disk)."""
    with session_scope() as s:
        row = s.get(ReceivedFile, file_id)
        if row is None:
            return None
        s.expunge(row)
    path = files_dir() / row.stored_as
    return (row, path.read_bytes()) if row.stored_as and path.is_file() else None


def mark_saved(file_id: int, link: str) -> None:
    with session_scope() as s:
        row = s.get(ReceivedFile, file_id)
        if row is not None:
            row.drive_link = link[:300]


@router.post("/api/files", status_code=201)
async def upload(file: UploadFile, folder_id: int | None = Form(default=None)) -> dict:
    data = await file.read(MAX_BYTES + 1)
    try:
        folder_name = ""
        if folder_id is not None:
            from junior.db import NotesFolder
            with session_scope() as s:
                folder = s.get(NotesFolder, folder_id)
                if folder is None:
                    raise HTTPException(422, "Choose an existing folder.")
                folder_name = folder.name
        number, label = save_received(data, file.filename or "file", file.content_type or "", "chat", library_folder=folder_name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"id": number, "tag": label}


@router.get("/api/files/{file_id}/download")
def download_generated(file_id: int):
    """Serve only application-generated artifacts; never accept a filesystem path from the model or URL."""
    with session_scope() as s:
        row = s.get(ReceivedFile, file_id)
        if row is None or row.source != "generated":
            raise HTTPException(404, "Generated file not found.")
        root = files_dir().resolve()
        path = root / row.stored_as
        if path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise HTTPException(404, "Generated file not found.")
        return FileResponse(path, media_type=row.mime, filename=row.filename,
                            headers={"X-Content-Type-Options": "nosniff"})
