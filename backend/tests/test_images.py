"""Images on drafts (P2-08)."""

import pytest
from fastapi.testclient import TestClient

from junior.approvals import create_item
from junior.main import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


def upload(client, item_id, data, name="shot.png"):
    return client.post(f"/api/approvals/{item_id}/images", files={"file": (name, data, "application/octet-stream")})


def test_add_view_and_remove_an_image(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    r = upload(client, item.id, PNG, "diagram.png")
    assert r.status_code == 201
    image = r.json()
    assert image["name"] == "diagram.png"

    got = client.get(image["url"])
    assert got.status_code == 200 and got.headers["content-type"] == "image/png" and got.content == PNG
    assert client.get(f"/api/approvals/{item.id}").json()["images"][0]["id"] == image["id"]
    assert upload(client, item.id, JPG, "photo.jpg").status_code == 201
    assert upload(client, item.id, WEBP, "x.webp").status_code == 201

    assert client.delete(f"/api/approvals/{item.id}/images/{image['id']}").status_code == 204
    assert client.get(image["url"]).status_code == 404
    assert len(client.get(f"/api/approvals/{item.id}").json()["images"]) == 2


def test_only_real_images_and_sensible_sizes(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    # The name says PNG, the bytes say otherwise.
    assert upload(client, item.id, b"<script>alert(1)</script>", "evil.png").status_code == 415
    assert upload(client, item.id, b"%PDF-1.7 ...", "doc.png").status_code == 415
    assert upload(client, item.id, PNG + b"\x00" * (10 * 1024 * 1024), "huge.png").status_code == 413
    for _ in range(10):
        assert upload(client, item.id, PNG).status_code == 201
    assert upload(client, item.id, PNG).status_code == 409  # 10 per draft
    assert upload(client, 999, PNG).status_code == 404


def test_instagram_posts_wait_for_an_image(client):
    item = create_item(kind="copy", platform="instagram", item_type="post", text="Caption")
    assert client.get(f"/api/approvals/{item.id}").json()["needs_image"] is True
    r = client.post(f"/api/approvals/{item.id}/posted")
    assert r.status_code == 409 and "need an image" in r.json()["detail"]

    upload(client, item.id, JPG, "photo.jpg")
    assert client.get(f"/api/approvals/{item.id}").json()["needs_image"] is False
    assert client.post(f"/api/approvals/{item.id}/posted").json()["status"] == "posted"

    # A comment on Instagram doesn't need one; a LinkedIn post doesn't either.
    comment = create_item(kind="copy", platform="instagram", item_type="comment", text="Nice!")
    assert comment.needs_image is False
    assert create_item(kind="copy", platform="linkedin", item_type="post", text="Hi").needs_image is False


def test_images_only_change_while_the_draft_waits(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    image = upload(client, item.id, PNG).json()
    client.post(f"/api/approvals/{item.id}/posted")
    assert upload(client, item.id, PNG).status_code == 409
    assert client.delete(f"/api/approvals/{item.id}/images/{image['id']}").status_code == 409
    assert client.get(image["url"]).status_code == 200  # still viewable


def test_list_filters_by_platform_and_includes_images(client):
    a = create_item(kind="copy", platform="linkedin", item_type="post", text="A")
    create_item(kind="copy", platform="x", item_type="post", text="B")
    upload(client, a.id, PNG)
    items = client.get("/api/approvals?status=all&platform=linkedin").json()
    assert [i["text"] for i in items] == ["A"] and len(items[0]["images"]) == 1


def test_removing_an_image_still_works_when_the_file_is_locked(client, monkeypatch):
    from pathlib import Path

    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    image = upload(client, item.id, PNG).json()

    def locked(self, missing_ok=False):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")

    monkeypatch.setattr(Path, "unlink", locked)
    assert client.delete(f"/api/approvals/{item.id}/images/{image['id']}").status_code == 204
    assert client.get(f"/api/approvals/{item.id}").json()["images"] == []
