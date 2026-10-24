"""Google Drive: find your files by name, fetch one to send to you, and save new files you send.

Existing files are only read by these tools. Saving adds new copies and never overwrites, moves or deletes originals.
The default connection uses drive.readonly + drive.file; optional broader Drive consent permits adding new files
inside folders the user created outside Junior. A save is never redirected to another destination.
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
        "POST", FILES, params={"fields": "id,name,webViewLink", "supportsAllDrives": "true"},
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
        "POST", UPLOAD, params={"uploadType": "multipart", "fields": "id,name,webViewLink", "supportsAllDrives": "true"},
        content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"},
    )


async def resolve_folder(folder: str, *, create: bool = False) -> dict:
    """Resolve an exact folder path or Google Drive folder URL; never choose between duplicate names."""
    from urllib.parse import urlparse
    folder = folder.strip()
    if folder.startswith(("https://", "http://")):
        url = urlparse(folder)
        match = re.fullmatch(r"/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/*", url.path)
        if url.scheme != "https" or url.hostname != "drive.google.com" or not match:
            raise GoogleError("Use a Google Drive folder link or an exact folder path such as University/NLP.")
        row = await call("GET", f"{FILES}/{match.group(1)}", params={"fields": "id,name,mimeType,trashed", "supportsAllDrives": "true"})
        if row.get("mimeType") != FOLDER or row.get("trashed"):
            raise GoogleError("That Drive link isn't an available folder.")
        return row
    parts = folder.replace("\\", "/").split("/") if folder else []
    if len(parts) > 12 or any(not p.strip() or p.strip() in (".", "..") for p in parts):
        raise GoogleError("Use a clear Drive folder path with at most 12 nonempty levels.")
    parent = {"id": "root", "name": "My Drive", "mimeType": FOLDER}
    for part in parts:
        part = part.strip()
        query = f"name = {_quoted(part)} and mimeType = '{FOLDER}' and {_quoted(parent['id'])} in parents and trashed = false"
        result = await call("GET", FILES, params={"q": query, "pageSize": "2", "fields": "nextPageToken,files(id,name,mimeType)",
                                                 "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        rows = result.get("files", [])
        if len(rows) > 1 or result.get("nextPageToken"):
            raise GoogleError(f"More than one Drive folder is named {part!r} here. Send the exact folder link.")
        if not rows and not create:
            raise GoogleError(f"Drive folder {part!r} was not found. Give the exact path or folder link.")
        parent = rows[0] if rows else await _new_folder(part, parent["id"])
    return parent


async def save_exact(name: str, data: bytes, mime: str, folder: str = "") -> dict:
    """Create a new file at precisely the requested destination. Never redirect to a fallback folder."""
    if len(data) > MAX_BYTES:
        raise GoogleError("The file is over the 20 MB Drive transfer limit.")
    parent = await resolve_folder(folder, create=True)
    try:
        return await _send_file(name, data, mime, parent["id"])
    except GoogleError as e:
        raise GoogleError(f"Couldn't confirm saving in the requested Drive folder. Check that folder before retrying. "
                          f"For an existing folder the app cannot access, use Settings → Connections → Allow existing Drive folders. {e}") from e


async def save_file(name: str, data: bytes, mime: str, folder: str = "") -> tuple[dict, str]:
    """Add a new file to your Drive, in a folder if you named one ("University" or "Work/Invoices").
    A folder that doesn't exist is made. Returns (the file, a note for you: '' or why it's somewhere else)."""
    return await save_exact(name, data, mime, folder), ""


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


# Google's own files, read as text.
AS_TEXT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",  # the first tab
    "application/vnd.google-apps.presentation": "text/plain",
}


async def for_reading(link: str) -> tuple[str, bytes, str]:
    """A file to read: (name, content, type). Google's own files come as text or CSV; others as they are."""
    fid = file_id(link)
    meta = await call("GET", f"{FILES}/{fid}", params={"fields": "id,name,mimeType,size"})
    name, mime = meta.get("name", "file"), meta.get("mimeType", "")
    if mime == FOLDER:
        raise GoogleError(f"{name!r} is a folder. Ask what's in it, or which file to read.")
    if mime in AS_TEXT:
        target = AS_TEXT[mime]
        return name + (".csv" if target == "text/csv" else ".txt"), await download(f"{FILES}/{fid}/export", params={"mimeType": target}), target
    if mime.startswith("application/vnd.google-apps."):
        raise GoogleError(f"{name!r} is a {kind(mime)}, which can't be read as a file.")
    if int(meta.get("size") or 0) > MAX_BYTES:
        raise GoogleError(f"{name!r} is too big to read here (over 20 MB).")
    return name, await download(f"{FILES}/{fid}", params={"alt": "media"}), mime


async def folder_contents(name: str, limit: int = 50) -> list[tuple[dict, list[dict]]]:
    """The folders whose names contain these words, each with what's in it (newest first). At most 3 folders."""
    words = [w for w in name.split() if w][:5]
    if not words:
        raise GoogleError("Tell me the folder's name.")
    q = " and ".join(f"name contains {_quoted(w)}" for w in words) + f" and mimeType = '{FOLDER}' and trashed = false"
    folders = (await call("GET", FILES, params={"q": q, "pageSize": "3", "fields": "files(id,name,webViewLink)"})).get("files", [])
    out = []
    for folder in folders:
        inside = await call(
            "GET", FILES,
            params={"q": f"{_quoted(folder['id'])} in parents and trashed = false", "orderBy": "folder,modifiedTime desc",
                    "pageSize": str(limit), "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"},
        )
        out.append((folder, inside.get("files", [])))
    return out


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
