"""Bounded new presentations through the official Slides API; no model-supplied API requests."""
from typing import Callable
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from junior.documents.schema import ResearchDocument, validate_document
from junior.google.auth import GoogleError, call

SLIDES = "https://slides.googleapis.com/v1/presentations"
MIME = "application/vnd.google-apps.presentation"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=1000)
    url: HttpUrl


class PresentationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: ResearchDocument
    sources: list[Citation] = Field(min_length=1, max_length=40)
    slide_count: int = Field(ge=1, le=24)

    def checked_sources(self):
        sources = [s.model_dump(mode="json") for s in self.sources]
        if len({s["id"] for s in sources}) != len(sources):
            raise ValueError("Source IDs must be unique.")
        validate_document(self.document, sources, "google_slides", self.slide_count)
        return sources


def slide_pages(doc, sources, count):
    """Complete visible pages plus speaker notes, including a final reference page."""
    catalog = {s["id"]: s for s in sources}
    pages = []
    for slide in doc.slides:
        refs = [catalog[i] for i in slide.source_ids]
        pages.append({"title": slide.title, "layout": slide.layout, "bullets": slide.bullets,
                      "references": ", ".join(f"[{s['id']}]" for s in refs),
                      "notes": slide.notes + "\n\nSources:\n" + "\n".join(
                          f"[{s['id']}] {s['title']}\n{s['url']}" for s in refs)})
    if count > 1:
        used = sorted({i for slide in doc.slides for i in slide.source_ids})
        pages.append({"title": "Sources", "layout": "sources", "bullets": [
            f"[{i}] {catalog[i]['title']}" for i in used], "references": "",
            "notes": "\n".join(f"[{i}] {catalog[i]['title']}\n{catalog[i]['url']}" for i in used),
            "links": [catalog[i]["url"] for i in used]})
    return pages


def requests_for(pages, width=720, height=405):
    """Fixed layout; scale against Google's actual default page size, in points."""
    requests = []
    def box(pid, key, text, x, y, w, h, size, color="162B45", bold=False, link=None):
        oid = f"{pid}_{key}"
        requests.append({"createShape": {"objectId": oid, "shapeType": "TEXT_BOX", "elementProperties": {
            "pageObjectId": pid, "size": {"width": {"magnitude": w * width, "unit": "PT"},
                                               "height": {"magnitude": h * height, "unit": "PT"}},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": x * width, "translateY": y * height, "unit": "PT"}}}})
        requests.append({"insertText": {"objectId": oid, "text": text, "insertionIndex": 0}})
        style = {"fontFamily": "Arial", "fontSize": {"magnitude": size, "unit": "PT"}, "bold": bold,
                 "foregroundColor": {"opaqueColor": {"rgbColor": {
                     c: int(color[n:n + 2], 16) / 255 for c, n in (("red", 0), ("green", 2), ("blue", 4))}}}}
        if link:
            style["link"] = {"url": link}
        requests.append({"updateTextStyle": {"objectId": oid, "textRange": {"type": "ALL"},
                                               "style": style, "fields": ",".join(style)}})
        direction = next((unicodedata.bidirectional(c) for c in text if unicodedata.bidirectional(c) in ("L", "R", "AL")), "L")
        if direction in ("R", "AL"):
            requests.append({"updateParagraphStyle": {"objectId": oid, "textRange": {"type": "ALL"},
                "style": {"direction": "RIGHT_TO_LEFT", "alignment": "END"}, "fields": "direction,alignment"}})

    for n, page in enumerate(pages):
        pid = f"junior_slide_{n:02d}"
        requests.append({"createSlide": {"objectId": pid, "slideLayoutReference": {"predefinedLayout": "BLANK"}}})
        box(pid, "title", page["title"], .055, .06, .89, .20, 26 if len(page["title"]) <= 100 else 20, bold=True)
        bullets = page["bullets"]
        if page["layout"] == "sources":
            # All references retained; two columns avoid silently dropping citations.
            rows = max(1, (len(bullets) + 1) // 2)
            for i, text in enumerate(bullets):
                short = text if len(text) <= 80 else text[:77] + "…"
                box(pid, f"ref{i}", short, .055 + (i // rows) * .455, .29 + (i % rows) * .60 / rows,
                    .44, .60 / rows, 12, "196CE6", link=page["links"][i])
        else:
            for i, text in enumerate(bullets):
                prefix = f"{i + 1}. " if page["layout"] == "steps" else "• "
                size = 18 if len(text) <= 110 else 14
                spacing = .60 / max(1, len(bullets))
                box(pid, f"body{i}", prefix + text, .065, .29 + i * spacing, .87, spacing, size)
        box(pid, "footer", ("Sources: " + page["references"] if page["references"] else "") +
            f"     {n + 1} / {len(pages)}", .055, .93, .89, .05, 9, "516277")
    return requests


async def create_presentation(payload: PresentationPayload, remember_created: Callable, before_write: Callable):
    sources = payload.checked_sources()  # Validate before the first remote write.
    pages = slide_pages(payload.document, sources, payload.slide_count)
    before_write()
    created = await call("POST", SLIDES, json={"title": payload.document.title})
    fid = created["presentationId"]
    link = f"https://docs.google.com/presentation/d/{fid}/edit"
    remember_created(fid, link)  # Persist immediately, including when formatting later fails.
    def points(dimension, fallback):
        part = created.get("pageSize", {}).get(dimension, {})
        return part.get("magnitude", fallback) / (12700 if part.get("unit") == "EMU" else 1)
    before_write()
    await call("POST", f"{SLIDES}/{fid}:batchUpdate",
               json={"requests": requests_for(pages, points("width", 720), points("height", 405))})
    got = await call("GET", f"{SLIDES}/{fid}", params={"fields": "slides(objectId,slideProperties(notesPage(notesProperties(speakerNotesObjectId))))"})
    notes = {s["objectId"]: s.get("slideProperties", {}).get("notesPage", {}).get("notesProperties", {}).get("speakerNotesObjectId")
             for s in got.get("slides", [])}
    requests = []
    for i, page in enumerate(pages):
        oid = notes.get(f"junior_slide_{i:02d}")
        if not oid:
            raise GoogleError("Slides were created, but Google did not return their speaker-note shapes.")
        requests.append({"insertText": {"objectId": oid, "insertionIndex": 0, "text": page["notes"]}})
    before_write()
    await call("POST", f"{SLIDES}/{fid}:batchUpdate", json={"requests": requests})
    return fid, link
