"""Google Docs: create a doc from text Junior Muneer wrote, and read one of yours by its link."""

import re

from junior.google.auth import GoogleError, call, download

DOCS = "https://docs.googleapis.com/v1/documents"
EXPORT = "https://www.googleapis.com/drive/v3/files/{id}/export"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_READ_CHARS = 20_000
MAX_WRITE_CHARS = 100_000
_ID = re.compile(r"/document/d/([A-Za-z0-9_-]+)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
HEADINGS = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3"}


def doc_id(link: str) -> str:
    """The doc's id from its link (or the id itself)."""
    link = link.strip()
    if m := _ID.search(link):
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
        return link
    raise GoogleError("That doesn't look like a Google Doc link (docs.google.com/document/d/...).")


def doc_link(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}/edit"


def layout(markdown: str) -> tuple[str, list[dict]]:
    """Light markdown as the doc's plain text, plus the requests that style it: # headings, - and 1. lists, **bold**.
    Indexes start at 1 (the start of a new doc's body)."""
    text_parts: list[str] = []
    styles: list[dict] = []
    index = 1
    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        kind, level = "text", 0
        if m := re.match(r"^(#{1,3})\s+(.*)$", line):
            kind, level, line = "heading", len(m.group(1)), m.group(2)
        elif m := re.match(r"^\s*[-*•]\s+(.*)$", line):
            kind, line = "bullet", m.group(1)
        elif m := re.match(r"^\s*\d+[.)]\s+(.*)$", line):
            kind, line = "number", m.group(1)
        bold: list[tuple[int, int]] = []
        plain = ""
        last = 0
        for b in _BOLD.finditer(line):
            plain += line[last : b.start()]
            bold.append((index + len(plain), index + len(plain) + len(b.group(1))))
            plain += b.group(1)
            last = b.end()
        plain += line[last:]
        start, end = index, index + len(plain) + 1  # with its newline
        rng = {"startIndex": start, "endIndex": end}
        if kind == "heading":
            styles.append({"updateParagraphStyle": {"range": rng, "paragraphStyle": {"namedStyleType": HEADINGS[level]}, "fields": "namedStyleType"}})
        elif kind in ("bullet", "number"):
            preset = "BULLET_DISC_CIRCLE_SQUARE" if kind == "bullet" else "NUMBERED_DECIMAL_ALPHA_ROMAN"
            styles.append({"createParagraphBullets": {"range": rng, "bulletPreset": preset}})
        for s, e in bold:
            styles.append({"updateTextStyle": {"range": {"startIndex": s, "endIndex": e}, "textStyle": {"bold": True}, "fields": "bold"}})
        text_parts.append(plain + "\n")
        index = end
    return "".join(text_parts), styles


async def create_doc(title: str, content: str) -> tuple[str, str]:
    """A new doc in your Drive with this content. Returns (id, link)."""
    if len(content) > MAX_WRITE_CHARS:
        raise GoogleError(f"That's too long for one doc (over {MAX_WRITE_CHARS:,} characters). Split it.")
    created = await call("POST", DOCS, json={"title": " ".join(title.split())[:200] or "Untitled"})
    document_id = created["documentId"]
    text, styles = layout(content)
    if text.strip():
        requests = [{"insertText": {"location": {"index": 1}, "text": text}}, *styles]
        await call("POST", f"{DOCS}/{document_id}:batchUpdate", json={"requests": requests})
    return document_id, doc_link(document_id)


async def export_docx(link: str) -> tuple[str, bytes]:
    """A doc as a Word file: (file name, content). Works for docs the app created (its Drive permission covers
    only those); for your other docs, Google says no and the link is sent instead."""
    document_id = doc_id(link)
    title = (await call("GET", f"{DOCS}/{document_id}", params={"fields": "title"})).get("title", "Document")
    data = await download(EXPORT.format(id=document_id), params={"mimeType": DOCX})
    safe = re.sub(r'[\\/:*?"<>|]+', " ", title).strip()[:80] or "Document"
    return f"{safe}.docx", data


def _text_of(elements: list[dict]) -> str:
    out = []
    for el in elements:
        if "paragraph" in el:
            out.append("".join(r.get("textRun", {}).get("content", "") for r in el["paragraph"].get("elements", [])))
        elif "table" in el:
            for row in el["table"].get("tableRows", []):
                cells = [_text_of(c.get("content", [])).strip().replace("\n", " ") for c in row.get("tableCells", [])]
                out.append(" | ".join(cells) + "\n")
    return "".join(out)


async def read_doc(link: str) -> tuple[str, str]:
    """(title, text) of a doc you can open. Long docs are cut at MAX_READ_CHARS."""
    document_id = doc_id(link)
    doc = await call("GET", f"{DOCS}/{document_id}")
    text = _text_of(doc.get("body", {}).get("content", [])).strip()
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + f"\n\n(cut here: the doc is longer than {MAX_READ_CHARS:,} characters)"
    return doc.get("title", "Untitled"), text
