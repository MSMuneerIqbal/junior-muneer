"""P3-02: Facebook Page posting through the Graph API (a fake Graph API: no network)."""

import asyncio
import hashlib
import hmac
import json
from urllib.parse import parse_qs

import httpx
import pytest

from junior.approvals import create_item
from junior.connect import exchange_meta, masked, set_env
from junior.senders.base import Outgoing
from junior.senders.dispatch import send_item
from junior.senders.facebook import FacebookPageSender, appsecret_proof
from junior.senders.registry import SenderRegistry

PAGE, TOKEN, SECRET = "1234567890", "EAAtestpagetoken", "s3cret"
BASE = "https://graph.facebook.com/v26.0"


class FakeGraph:
    """Answers like the Graph API and records every request."""

    def __init__(self, fail: dict[str, tuple[int, dict]] | None = None):
        self.calls: list[tuple[str, str, dict, bytes]] = []
        self.fail = fail or {}
        self.photos = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v26.0/")
        body = request.content
        form = {k: v[0] for k, v in parse_qs(body.decode(errors="ignore")).items()} if b"form-data" not in request.headers.get("content-type", "").encode() else {}
        self.calls.append((request.method, path, {**dict(request.url.params), **form}, body))
        if path in self.fail:
            status, err = self.fail[path]
            return httpx.Response(status, json=err)
        if path == f"{PAGE}/feed":
            return httpx.Response(200, json={"id": f"{PAGE}_555"})
        if path == f"{PAGE}/photos":
            self.photos += 1
            return httpx.Response(200, json={"id": f"photo{self.photos}", "post_id": f"{PAGE}_777"})
        if request.method == "GET" and path.startswith(f"{PAGE}_"):
            return httpx.Response(200, json={"permalink_url": f"https://www.facebook.com/page/posts/{path}"})
        if request.method == "GET" and path == PAGE:
            return httpx.Response(200, json={"name": "Muneer AI", "id": PAGE})
        return httpx.Response(404, json={"error": {"message": "unknown", "code": 100}})


def sender(graph: FakeGraph, secret: str = SECRET) -> FacebookPageSender:
    return FacebookPageSender(PAGE, TOKEN, secret, "v26.0", transport=httpx.MockTransport(graph))


def out(text="Hello Facebook", images=()):
    return Outgoing(1, "facebook.page.post", "facebook", "post", text, tuple(images))


def run(coro):
    return asyncio.run(coro)


def test_a_text_post_with_appsecret_proof_and_permalink():
    graph = FakeGraph()
    result = run(sender(graph).send(out("Launch day!")))
    assert result.outcome == "sent" and result.remote_id == f"{PAGE}_555"
    assert result.url == f"https://www.facebook.com/page/posts/{PAGE}_555"
    method, path, params, _ = graph.calls[0]
    assert (method, path) == ("POST", f"{PAGE}/feed")
    assert params["message"] == "Launch day!" and params["access_token"] == TOKEN
    assert params["appsecret_proof"] == hmac.new(SECRET.encode(), TOKEN.encode(), hashlib.sha256).hexdigest()
    assert appsecret_proof(TOKEN, SECRET) == params["appsecret_proof"]


def test_one_image_is_a_photo_post_with_a_caption(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    graph = FakeGraph()
    result = run(sender(graph).send(out("With a picture", [img])))
    assert result.outcome == "sent" and result.remote_id == f"{PAGE}_777"
    method, path, _, body = graph.calls[0]
    assert (method, path) == ("POST", f"{PAGE}/photos")
    assert b'name="caption"' in body and b"With a picture" in body and b'name="published"' in body and b"true" in body
    assert b'filename="shot.png"' in body and b"\x89PNG" in body


def test_several_images_are_uploaded_unpublished_then_posted_together(tmp_path):
    images = []
    for n in range(2):
        p = tmp_path / f"slide{n}.jpg"
        p.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        images.append(p)
    graph = FakeGraph()
    result = run(sender(graph).send(out("Two slides", images)))
    assert result.outcome == "sent"
    uploads = [c for c in graph.calls if c[1] == f"{PAGE}/photos"]
    assert len(uploads) == 2 and all(b"false" in c[3] for c in uploads)  # published=false
    feed = next(c for c in graph.calls if c[1] == f"{PAGE}/feed")
    assert json.loads(feed[2]["attached_media[0]"]) == {"media_fbid": "photo1"}
    assert json.loads(feed[2]["attached_media[1]"]) == {"media_fbid": "photo2"}
    assert feed[2]["message"] == "Two slides"


@pytest.mark.parametrize(
    ("status", "error", "outcome", "words"),
    [
        (400, {"error": {"message": "Error validating access token", "code": 190}}, "failed", "Run connect.bat meta again"),
        (403, {"error": {"message": "(#200) Permissions error", "code": 200}}, "failed", "a permission is missing"),
        (400, {"error": {"message": "Abusive", "code": 368}}, "failed", "possibly abusive"),
        (400, {"error": {"message": "Please retry", "code": 2, "is_transient": True}}, "failed", "temporary problem"),
        (500, {"error": {"message": "Internal"}}, "unclear", "may or may not have posted"),
    ],
    ids=["expired-token", "permission", "abusive", "transient", "server-error"],
)
def test_errors_are_failed_or_unclear(status, error, outcome, words):
    graph = FakeGraph(fail={f"{PAGE}/feed": (status, error)})
    result = run(sender(graph).send(out()))
    assert result.outcome == outcome and words in result.detail


def test_a_missing_permalink_still_counts_as_posted():
    graph = FakeGraph(fail={f"{PAGE}_555": (400, {"error": {"message": "nope", "code": 100}})})
    result = run(sender(graph).send(out()))
    assert result.outcome == "sent" and result.url == f"https://www.facebook.com/{PAGE}_555"


def test_the_connection_check():
    assert run(sender(FakeGraph()).check()) == "Connected to the Page “Muneer AI”."
    expired = FakeGraph(fail={PAGE: (400, {"error": {"message": "expired", "code": 190}})})
    assert "Run connect.bat meta again" in run(sender(expired).check())


def test_approve_and_post_through_the_page(tmp_path):
    graph = FakeGraph()
    registry = SenderRegistry([sender(graph)])
    item = create_item(kind="api", platform="facebook", item_type="post", text="Hello from Junior Muneer", action_type="facebook.page.post")
    from junior.approvals import approve_item

    approve_item(item.id)
    posted = run(send_item(item.id, registry))
    assert posted.status == "posted" and posted.meta["post_url"].endswith(f"{PAGE}_555")
    assert graph.calls[0][2]["message"] == "Hello from Junior Muneer"


def test_the_page_sender_is_used_when_connected(monkeypatch):
    from junior.config import get_settings
    from junior.main import default_senders

    assert default_senders(get_settings()).for_action("facebook.page.post") is None  # not connected, no fake
    monkeypatch.setenv("META_PAGE_ID", PAGE)
    monkeypatch.setenv("META_PAGE_TOKEN", TOKEN)
    get_settings.cache_clear()
    found = default_senders(get_settings()).for_action("facebook.page.post")
    assert isinstance(found, FacebookPageSender) and found.page_id == PAGE


# ---- connecting -------------------------------------------------------------------------


def test_exchange_meta_gets_long_lived_page_tokens():
    seen = []

    def graph(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("oauth/access_token"):
            return httpx.Response(200, json={"access_token": "LONGUSER"})
        return httpx.Response(200, json={"data": [{"id": PAGE, "name": "Muneer AI", "access_token": "PAGETOKEN", "tasks": ["CREATE_CONTENT"]}]})

    pages = run(exchange_meta("123456", SECRET, "SHORT", transport=httpx.MockTransport(graph)))
    assert pages[0]["access_token"] == "PAGETOKEN"
    exchange, accounts = seen
    assert exchange[1]["grant_type"] == "fb_exchange_token" and exchange[1]["fb_exchange_token"] == "SHORT"
    assert accounts[1]["access_token"] == "LONGUSER" and accounts[1]["appsecret_proof"] == appsecret_proof("LONGUSER", SECRET)


def test_set_env_replaces_and_keeps_everything_else(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-keep\n# a comment\nMETA_PAGE_ID=old\n", encoding="utf-8")
    set_env({"META_PAGE_ID": PAGE, "META_PAGE_TOKEN": TOKEN}, env)
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-keep" in text and "# a comment" in text
    assert f"META_PAGE_ID={PAGE}" in text and "META_PAGE_ID=old" not in text
    assert f"META_PAGE_TOKEN={TOKEN}" in text
    assert masked("EAAAbcdefghijklmnop") == "EAAA…mnop" and TOKEN not in masked(TOKEN)
