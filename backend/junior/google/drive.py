"""Google Drive: find your files by name, fetch one to send to you, and save new files you send.

Your existing files are read-only to the app (`drive.readonly`): it can see and download them, never change,
move or delete them. Saving only ever adds new files (`drive.file`), so nothing is overwritten.
Google's own files are exported (a Doc as Word or PDF, a Sheet as Excel, Slides as PowerPoint or PDF);
everything else comes as it is.
"""

import json
import re
import uuid

from junior.google.auth import GoogleError, call, download

FILES = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
MAX_BYTES = 20 * 1024 * 1024  # fits a Gmail attachment and a WhatsApp document
FOLDER = "application/vnd.google-apps.folder"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF = "application/pdf"
# Google's own types: what they become, and the file ending.
EXPORTS = {
    "application/vnd.google-apps.document": (DOCX, ".docx"),
    "application/vnd.google-apps.spreadsheet": (XLSX, ".xlsx"),
    "application/vnd.google-apps.presentation": (PPTX, ".pptx"),
    "application/vnd.google-apps.drawing": (PDF, ".pdf"),
}
KINDS = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    FOLDER: "folder",
    PDF: "PDF",
    DOCX: "Word file",
    "application/msword": "Word file",
    XLSX: "Excel file",
    PPTX: "PowerPoint file",
}
_LINK_ID = re.compile(r"/(?:file|document|spreadsheets|presentation|drawings)/d/([A-Za-z0-9_-]+)|[?&]id=([A-Za-z0-9_-]+)")


def file_id(link: str) -> str:
    """A Drive file's id from any of its links (or the id itself)."""
    link = link.strip()
    if m := _LINK_ID.search(link):
        return m.group(1) or m.group(2)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
        return link
    raise GoogleError("That doesn't look like a Google Drive link.")


def kind(mime: str) -> str:
    if mime in KINDS:
        return KINDS[mime]
    if mime.startswith("image/"):
        return "image"
    return mime.rsplit("/", 1)[-1] or "file"


def _quoted(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


async def _folder_named(name: str, parent: str) -> dict | None:
    q = f"name = {_quoted(name)} and mimeType = '{FOLDER}' and {_quoted(parent)} in parents and trashed = false"
    got = await call("GET", FILES, params={"q": q, "pageSize": "1", "fields": "files(id,name,webViewLink)"})
    return (got.get("files") or [None])[0]


async def _new_folder(name: str, parent: str) -> dict:
    return await call(
        "POST", FILES, params={"fields": "id,name,webViewLink"},
        json={"name": name, "mimeType": FOLDER, "parents": [parent]},
    )


async def _send_file(name: str, data: bytes, mime: str, parent: str) -> dict:
    """One multipart upload: the file's details and its content together."""
    boundary = f"junior{uuid.uuid4().hex}"
    meta = json.dumps({"name": name, "parents": [parent]})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: {mime or 'application/octet-stream'}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return await call(
        "POST", UPLOAD, params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
        content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"},
    )


async def save_file(name: str, data: bytes, mime: str, folder: str = "") -> tuple[dict, str]:
    """Add a new file to your Drive, in a folder if you named one ("University" or "Work/Invoices").
    A folder that doesn't exist is made. Returns (the file, a note for you: '' or why it's somewhere else)."""
    if len(data) > MAX_BYTES:
        raise GoogleError("That file is too big to save from here (over 20 MB).")
    parent, note = "root", ""
    names = [p.strip() for p in folder.replace("\\", "/").split("/") if p.strip()][:5]
    for part in names:
        found = await _folder_named(part, parent)
        parent = found["id"] if found else (await _new_folder(part, parent))["id"]
    try:
        return await _send_file(name, data, mime, parent), note
    except GoogleError as e:
        refused = "access" in str(e).lower() or "find" in str(e).lower()  # Google's 403 / 404 for the folder
        if parent == "root" or not refused:
            raise
    # Your own folder: the app's permission covers only files and folders it made. Use one it made, next to yours.
    fallback = " ".join(names) + " (Junior Muneer)"
    found = await _folder_named(fallback, "root")
    parent = found["id"] if found else (await _new_folder(fallback, "root"))["id"]
    note = (
        f"Google didn't let the app put it into your own folder {folder!r} (the app may only add to folders it made), "
        f"so it's in a new folder {fallback!r}. You can drag it across in Drive."
    )
    return await _send_file(name, data, mime, parent), note


async def search(words: str, limit: int = 10) -> list[dict]:
    """Your files whose names contain all these words (not in the trash), newest first."""
    terms = [w for w in re.split(r"\s+", words.strip()) if w][:6]
    if not terms:
        raise GoogleError("Tell me some words from the file's name.")
    query = " and ".join("name contains '{}'".format(t.replace("\\", "\\\\").replace("'", "\\'")) for t in terms)
    got = await call(
        "GET",
        FILES,
        params={
            "q": f"{query} and trashed = false",
            "orderBy": "modifiedTime desc",
            "pageSize": str(max(1, min(limit, 25))),
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
        },
    )
    return got.get("files", [])


async def fetch(link: str, as_pdf: bool = False) -> tuple[str, bytes, str]:
    """A file to send: (file name, content, type). Google's own files are exported; as_pdf turns Docs and Slides into PDF."""
    fid = file_id(link)
    meta = await call("GET", f"{FILES}/{fid}", params={"fields": "id,name,mimeType,size"})
    name, mime = meta.get("name", "file"), meta.get("mimeType", "")
    if mime == FOLDER:
        raise GoogleError(f"{name!r} is a folder, not a file. Ask which file in it.")
    if int(meta.get("size") or 0) > MAX_BYTES:
        raise GoogleError(f"{name!r} is too big to send (over 20 MB). Send its link instead.")
    if mime in EXPORTS:
        target, ending = EXPORTS[mime]
        if as_pdf and mime != "application/vnd.google-apps.spreadsheet":
            target, ending = PDF, ".pdf"
        data = await download(f"{FILES}/{fid}/export", params={"mimeType": target})
        mime = target
        name = name if name.lower().endswith(ending) else name + ending
    elif mime.startswith("application/vnd.google-apps."):
        raise GoogleError(f"{name!r} is a {kind(mime)}, which can't be downloaded as a file. Send its link instead.")
    else:
        data = await download(f"{FILES}/{fid}", params={"alt": "media"})
    if len(data) > MAX_BYTES:
        raise GoogleError(f"{name!r} is too big to send (over 20 MB). Send its link instead.")
    return re.sub(r'[\\/:*?"<>|]+', " ", name).strip()[:120] or "file", data, mime
