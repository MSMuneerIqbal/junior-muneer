from typing import Annotated, Literal
from pydantic import BaseModel, Field

Short = Annotated[str, Field(min_length=1, max_length=160)]
Bullet = Annotated[str, Field(min_length=1, max_length=180)]
SLIDE_FORMATS = ("pptx", "google_slides", "slides_pdf")
FORMATS = (*SLIDE_FORMATS, "pdf", "docx", "markdown", "xlsx", "google_doc", "google_sheet")


class Slide(BaseModel):
    title: Short
    layout: Literal["cover", "points", "comparison", "steps"]
    bullets: list[Bullet] = Field(max_length=5)
    notes: str = Field(max_length=1800)
    source_ids: list[int] = Field(max_length=8)


class Section(BaseModel):
    heading: Short
    text: str = Field(min_length=1, max_length=4500)
    source_ids: list[int] = Field(max_length=8)


class ResearchDocument(BaseModel):
    title: Short
    summary: str = Field(min_length=1, max_length=1200)
    sections: list[Section] = Field(max_length=16)
    slides: list[Slide] = Field(max_length=24)
    headers: list[Short] = Field(max_length=12)
    rows: list[list[str]] = Field(max_length=100)


class DocumentReview(BaseModel):
    passes: bool
    issues: list[str] = Field(max_length=12)


def validate_document(doc: ResearchDocument, sources: list[dict], output_format: str, count: int) -> None:
    known = {s["id"] for s in sources}
    parts = doc.slides if output_format in SLIDE_FORMATS else doc.sections if output_format not in ("xlsx", "google_sheet") else []
    for n, part in enumerate(parts):
        cover = output_format in SLIDE_FORMATS and n == 0 and part.layout == "cover"
        label = f"slide {n + 1}: {part.title}" if output_format in SLIDE_FORMATS else f"section: {part.heading}"
        if not set(part.source_ids) <= known:
            raise ValueError(f"Unknown source IDs on {label}. Use only catalog IDs {sorted(known)}.")
        if not part.source_ids and not cover:
            raise ValueError(f"Missing source IDs on {label}. Cite supporting catalog IDs from {sorted(known)}.")
    if output_format in ("docx", "markdown", "google_doc", "pdf") and not doc.sections:
        raise ValueError("A written report needs complete sections with cited source IDs.")
    if output_format in SLIDE_FORMATS:
        if not any(slide.source_ids for slide in doc.slides):
            raise ValueError("A researched presentation needs at least one cited source, including a single-slide presentation.")
        if len({i for slide in doc.slides for i in slide.source_ids}) > 12:
            raise ValueError("Use at most 12 distinct sources across a slide deck so its reference slide stays readable.")
        expected = count - 1 if count > 1 else 1  # the exporter adds the sources slide
        if len(doc.slides) != expected:
            raise ValueError(f"Provide exactly {expected} content slides; the exporter adds sources when needed.")
        if any(not slide.bullets for slide in doc.slides):
            raise ValueError("Each slide needs content, not just a title.")
        if count > 1 and doc.slides[0].layout == "cover" and len(doc.slides[0].bullets) > 2:
            raise ValueError("Keep the cover to at most two short bullets; put the other points on content slides.")
    if output_format in ("xlsx", "google_sheet"):
        if not doc.headers or not doc.rows:
            raise ValueError("A spreadsheet needs headers and evidence-backed rows.")
        if any(len(r) != len(doc.headers) or any(len(c) > 2000 for c in r) for r in doc.rows):
            raise ValueError("Spreadsheet rows must match the headers and use short cells.")
        catalog_urls = {s["url"] for s in sources}
        if any(not any(c in catalog_urls for c in row) for row in doc.rows):
            raise ValueError("Each spreadsheet row must include a real catalog URL in a source column.")
