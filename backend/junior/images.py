"""Your images, attached to drafts (P2-08).

Saved in data/uploads/images. Only real JPEG, PNG, WebP or GIF files (checked by their
first bytes, not their name), up to 10 MB each, 10 per draft. Copy-and-paste items: you
download the image and add it on the platform yourself.

    POST   /api/approvals/{id}/images            upload (multipart, field "file")
    DELETE /api/approvals/{id}/images/{image_id}
    GET    /api/images/{image_id}                the file
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from junior.audit import audit
from junior.config import get_settings
from junior.db import ApprovalItem, Image, session_scope

log = logging.getLogger(__name__)
router = APIRouter()

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_ITEM = 10
# First bytes of each allowed type -> (extension, content type).
SIGNATURES = [
    (b"\xff\xd8\xff", ("jpg", "image/jpeg")),
    (b"\x89PNG\r\n\x1a\n", ("png", "image/png")),
    (b"GIF87a", ("gif", "image/gif")),
    (b"GIF89a", ("gif", "image/gif")),
]


def images_dir() -> Path:
    path = get_settings().data_path / "uploads" / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff(head: bytes) -> tuple[str, str] | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    return next((kind for sig, kind in SIGNATURES if head.startswith(sig)), None)


def image_url(image_id: int) -> str:
    return f"/api/images/{image_id}"


def images_for(item_ids: list[int]) -> dict[int, list[dict]]:
    with session_scope() as s:
        rows = s.scalars(select(Image).where(Image.approval_id.in_(item_ids)).order_by(Image.id)).all()
        found: dict[int, list[dict]] = {}
        for i in rows:
            found.setdefault(i.approval_id, []).append(
                {"id": i.id, "url": image_url(i.id), "name": i.original_name, "size": i.size}
            )
        return found


@router.post("/api/approvals/{item_id}/images", status_code=201)
async def upload(item_id: int, file: UploadFile) -> dict:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That image is over 10 MB. Please use a smaller one.")
    kind = sniff(data[:16])
    if kind is None:
        raise HTTPException(415, "Only JPEG, PNG, WebP or GIF images can be added.")
    ext, content_type = kind
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        if item is None:
            raise HTTPException(404, f"Approval item {item_id} doesn't exist.")
        if item.status != "waiting":
            raise HTTPException(409, f"This item is {item.status.replace('_', ' ')}; images can only change while it waits.")
        count = len(s.scalars(select(Image.id).where(Image.approval_id == item_id)).all())
        if count >= MAX_PER_ITEM:
            raise HTTPException(409, f"A draft can have at most {MAX_PER_ITEM} images.")
        name = f"{uuid.uuid4().hex}.{ext}"
        (images_dir() / name).write_bytes(data)
        image = Image(
            approval_id=item_id,
            file=name,
            original_name=(file.filename or f"image.{ext}")[:200],
            content_type=content_type,
            size=len(data),
        )
        s.add(image)
        s.flush()
        out = {"id": image.id, "url": image_url(image.id), "name": image.original_name, "size": image.size}
    audit("action", "image_added", detail={"approval": item_id, "image": out["id"], "size": out["size"]})
    return out


@router.delete("/api/approvals/{item_id}/images/{image_id}", status_code=204)
def remove(item_id: int, image_id: int) -> None:
    with session_scope() as s:
        image = s.get(Image, image_id)
        if image is None or image.approval_id != item_id:
            raise HTTPException(404, "That image isn't on this draft.")
        if s.get(ApprovalItem, item_id).status != "waiting":
            raise HTTPException(409, "Images can only change while the draft waits.")
        try:
            (images_dir() / image.file).unlink(missing_ok=True)
        except OSError:  # Windows: the browser may still be loading it; the file is left behind, harmless
            log.warning("Couldn't delete image file %s now; it is no longer attached", image.file)
        s.delete(image)
    audit("action", "image_removed", detail={"approval": item_id, "image": image_id})


@router.get("/api/images/{image_id}")
def get_image(image_id: int) -> FileResponse:
    with session_scope() as s:
        image = s.get(Image, image_id)
        if image is None:
            raise HTTPException(404, "No such image.")
        path, content_type, name = images_dir() / image.file, image.content_type, image.original_name
    if not path.exists():
        raise HTTPException(404, "The image file is missing.")
    return FileResponse(path, media_type=content_type, filename=name, content_disposition_type="inline")
