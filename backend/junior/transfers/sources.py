"""Resolve sources without exposing binary content to the model; pin approved bytes with SHA-256."""
import hashlib
import mimetypes

from sqlalchemy import select

from junior.computer.paths import check, recheck
from junior.computer.tools import _reading_refusal
from junior.db import Message, session_scope
from junior.files import TAG, received, safe_name, save_received

MAX_FILE_BYTES = 25 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pc_path(context, text):
    if why := _reading_refusal():
        raise ValueError(why)
    return check(text, context)


async def source_file(context, file_number=0, pc_file="", drive_link="", note_id=0):
    if sum(bool(v) for v in (file_number, pc_file, drive_link, note_id)) != 1:
        raise ValueError("Choose exactly one source: an uploaded/generated file number, PC file, Google Drive link or saved note ID.")
    if file_number:
        got = received(file_number)
        if got is None:
            from junior.db import ReceivedFile
            with session_scope() as s:
                row = s.get(ReceivedFile, file_number)
                if row and row.source == "drive" and row.library_folder_id is not None:
                    from junior.google.drive import fetch
                    link = row.drive_link
                else:
                    link = ""
            if link:
                return await fetch(link)
            raise ValueError("That source file is missing. Attach it again.")
        row, data = got
        with session_scope() as s:
            texts = s.scalars(select(Message.content).where(Message.id.in_(context.user_message_ids), Message.source == "user")).all()
        allowed = {int(n) for text in texts for n in TAG.findall(text)}
        if file_number not in allowed and row.library_folder_id is None and not (row.source == "generated" and row.conversation_id == context.conversation_id):
            raise ValueError("That file wasn't supplied or generated in this chat. Attach it here first.")
        return row.filename, data, row.mime
    if pc_file:
        path = pc_path(context, pc_file)
        if not path.is_file():
            raise ValueError(f"{path} isn't a file.")
        recheck(str(path))
        with path.open("rb") as f:
            data = f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Use a file under 25 MB.")
        return path.name, data, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if drive_link:
        from junior.google.drive import fetch
        return await fetch(drive_link)
    from junior.notes.store import markdown
    from junior.db import ClassNote
    with session_scope() as s:
        note = s.get(ClassNote, note_id)
        if note is None:
            raise ValueError("That saved note wasn't found.")
        return safe_name(f"{note.class_date} {note.title}.md"), markdown(note).encode("utf-8"), "text/markdown"


def snapshot(context, name, data, mime):
    number, _ = save_received(data, name, mime, "generated", context.conversation_id, index_in_library=False)
    return {"snapshot_id": number, "sha256": digest(data), "filename": safe_name(name), "bytes": len(data)}


def pinned(meta):
    got = received(int(meta["snapshot_id"]))
    if got is None or got[0].source != "generated" or digest(got[1]) != meta.get("sha256"):
        raise ValueError("The prepared file changed or is missing. Ask Junior to prepare it again.")
    return got
