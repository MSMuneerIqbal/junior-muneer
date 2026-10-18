"""Google Drive, read-only: find your files by name and fetch one to send to you (your CV, a PDF, a doc...).

The permission is `drive.readonly`: the app can see and download your files, never change, move or delete them.
Google's own files are exported (a Doc as Word or PDF, a Sheet as Excel, Slides as PowerPoint or PDF);
everything else comes as it is.
"""

import re

from junior.google.auth import GoogleError, call, download

FILES = "https://www.googleapis.com/drive/v3/files"
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
