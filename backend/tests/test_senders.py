"""P3-01: the API sender base: Safety Guard, exact approved text, run at most once, check manually."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from junior.approvals import create_item
from junior.db import ActionRun, ApprovalItem, session_scope
from junior.main import create_app
from junior.pause import set_paused
from junior.permissions import set_mode, set_rule
from junior.senders.base import SendResult, result_from_http_error
from junior.senders.dispatch import SendError, send_item
from junior.senders.fake import FakeSender
from junior.senders.registry import SenderRegistry
from junior.settings_store import set_setting

ALL = ("linkedin.post", "facebook.page.post", "instagram.post")


@pytest.fixture
def sender():
    return FakeSender("LinkedIn (fake)", ALL)


@pytest.fixture
def client(sender):
    with TestClient(create_app(model_provider=lambda: (lambda n: None), senders=lambda: SenderRegistry([sender]))) as c:
        yield c


def api_item(text="Hello LinkedIn", platform="linkedin", action="linkedin.post", **kw):
    return create_item(kind="api", platform=platform, item_type="post", text=text, action_type=action, **kw)


def runs():
    with session_scope() as s:
        return [(r.key, r.status) for r in s.scalars(select(ActionRun).order_by(ActionRun.id))]


def test_approving_sends_exactly_the_approved_text_once(client, sender):
    item = api_item("Hello LinkedIn")
    client.patch(f"/api/approvals/{item.id}", json={"text": "Hello LinkedIn, edited by me"})
    posted = client.post(f"/api/approvals/{item.id}/approve", json={}).json()
    assert posted["status"] == "posted"
    assert posted["meta"]["post_url"] == f"https://example.invalid/fake-posts/{item.id}"
    assert [o.text for o in sender.sent] == ["Hello LinkedIn, edited by me"]
    assert runs() == [(f"approval-{item.id}-attempt-1", "done")]

    r = client.post(f"/api/approvals/{item.id}/send")
    assert r.status_code == 409 and "isn't approved (it's posted)" in r.json()["detail"]
    assert len(sender.sent) == 1  # never twice
    names = [a["name"] for a in client.get("/api/activity?kind=action").json()]
    assert "posted" in names


def test_a_clear_failure_stays_approved_and_is_only_retried_by_hand(client, sender):
    item = api_item("[fail] Hello")
    out = client.post(f"/api/approvals/{item.id}/approve", json={}).json()
    assert out["status"] == "approved" and "refused it" in out["meta"]["last_error"]
    assert sender.sent == []
    again = client.post(f"/api/approvals/{item.id}/send").json()  # you try again, on purpose
    assert again["meta"]["attempts"] == 2
    assert runs() == [(f"approval-{item.id}-attempt-1", "failed"), (f"approval-{item.id}-attempt-2", "failed")]


def test_an_unclear_result_is_checked_by_you_never_retried(client, sender):
    item = api_item("[unclear] Hello")
    out = client.post(f"/api/approvals/{item.id}/approve", json={}).json()
    assert out["status"] == "check_manually" and "didn't answer clearly" in out["meta"]["last_error"]
    assert client.post(f"/api/approvals/{item.id}/send").status_code == 409  # no automatic second try

    assert client.post(f"/api/approvals/{item.id}/resolve", json={"posted": False}).json()["status"] == "approved"
    assert client.post(f"/api/approvals/{item.id}/resolve", json={"posted": True}).status_code == 409  # not unclear now

    other = api_item("[unclear] Second")
    client.post(f"/api/approvals/{other.id}/approve", json={})
    assert client.post(f"/api/approvals/{other.id}/resolve", json={"posted": True}).json()["status"] == "posted"


def _approve_then(client, item, change):
    client.post(f"/api/approvals/{item.id}/approve", json={})  # sent or blocked
    return change


@pytest.mark.parametrize(
    ("setup", "problem"),
    [
        ("tampered", "isn't exactly the text that was approved"),
        ("api key", "contains an API key"),
        ("placeholder", "placeholder"),
        ("too long", "Too long for LinkedIn"),
        ("paused", "Everything is paused"),
        ("denied", "Never runs"),
        ("manual mode", "needs your OK"),
        ("daily limit", "Today's limit is reached"),
    ],
)
def test_the_safety_guard_blocks_before_anything_is_sent(client, sender, setup, problem):
    text = {
        "api key": "My key is sk-proj-abcdefghijklmnopqrstuvwx123",
        "placeholder": "Read more here: [link]",
        "too long": "word " * 700,
    }.get(setup, "Hello LinkedIn")
    if setup == "manual mode":
        set_rule("linkedin.post", "auto")
    item = api_item(text)
    if setup == "daily limit":
        set_setting("api_posts_per_day", 1)
        first = api_item("An earlier post")
        client.post(f"/api/approvals/{first.id}/approve", json={})
    if setup == "manual mode":
        assert item.status == "approved"  # your Auto rule approved it...
        set_mode("ask_all")  # ...but now you want to OK everything
    else:
        client_items = client.post(f"/api/approvals/{item.id}/approve", json={}).json()
        if setup in ("api key", "placeholder", "too long", "daily limit"):
            assert client_items["status"] == "approved"  # approved, but the guard stopped the send
    if setup == "tampered":
        # Approve normally first? Sent already, so make a new approved item and change its text behind our back.
        item = api_item("Hello again")
        set_paused(True)
        client.post(f"/api/approvals/{item.id}/approve", json={})
        set_paused(False)
        with session_scope() as s:
            s.get(ApprovalItem, item.id).text = "Something else"
    if setup == "paused":
        item = api_item("Hello while paused")
        set_paused(True)
        client.post(f"/api/approvals/{item.id}/approve", json={})
    if setup == "denied":
        item = api_item("Hello then denied")
        set_paused(True)
        client.post(f"/api/approvals/{item.id}/approve", json={})
        set_paused(False)
        set_rule("linkedin.post", "deny")

    sent_before = len(sender.sent)
    r = client.post(f"/api/approvals/{item.id}/send")
    assert r.status_code == 409 and problem in r.json()["detail"]
    assert len(sender.sent) == sent_before  # nothing went out
    with session_scope() as s:
        assert s.get(ApprovalItem, item.id).status == "approved"


def test_a_platform_that_isnt_connected(client):
    item = api_item("Hello Facebook", platform="facebook", action="facebook.page.post")
    with TestClient(create_app(model_provider=lambda: (lambda n: None), senders=lambda: SenderRegistry())) as c:
        out = c.post(f"/api/approvals/{item.id}/approve", json={}).json()
        assert out["status"] == "approved"  # approved; it can be sent once Facebook is connected
        r = c.post(f"/api/approvals/{item.id}/send")
        assert r.status_code == 409 and "Facebook isn't connected yet" in r.json()["detail"]


class Broken:
    label = "LinkedIn (broken)"
    action_types = ("linkedin.post",)

    def __init__(self, mode):
        self.mode = mode

    def is_connected(self):
        return True

    async def send(self, out):
        if self.mode == "crash":
            raise RuntimeError("boom")
        await asyncio.sleep(5)
        return SendResult("sent")


@pytest.mark.parametrize("mode", ["crash", "slow"])
def test_a_crash_or_no_answer_means_check_manually(mode, monkeypatch):
    import junior.senders.dispatch as dispatch

    monkeypatch.setattr(dispatch, "SEND_SECONDS", 0.2)
    with TestClient(create_app(model_provider=lambda: (lambda n: None), senders=lambda: SenderRegistry([Broken(mode)]))) as c:
        item = api_item("Hello")
        out = c.post(f"/api/approvals/{item.id}/approve", json={}).json()
    assert out["status"] == "check_manually"
    assert ("RuntimeError" if mode == "crash" else "didn't answer in") in out["meta"]["last_error"]


def test_sending_twice_at_the_same_moment_posts_once():
    class Slow(FakeSender):
        async def send(self, out):
            await asyncio.sleep(0.2)
            return await super().send(out)

    slow = Slow("LinkedIn (slow)", ALL)
    senders = SenderRegistry([slow])
    item = api_item("Hello")
    with session_scope() as s:
        row = s.get(ApprovalItem, item.id)
        row.status = "approved"
        row.meta = {"approved_text": "Hello", "approved_by": "you"}

    async def both():
        return await asyncio.gather(send_item(item.id, senders), send_item(item.id, senders), return_exceptions=True)

    results = asyncio.run(both())
    assert len(slow.sent) == 1
    assert sum(isinstance(r, SendError) and "won't be sent twice" in str(r) for r in results) == 1


def test_drafts_become_api_items_only_for_connected_platforms():
    from junior.agent.context import TurnContext
    from junior.agent.tools import add_to_approvals_for
    from junior.senders import registry
    from junior.settings_store import all_settings

    context = TurnContext(conversation_id=None, settings=all_settings())
    registry.set_current(SenderRegistry([FakeSender("LinkedIn (fake)", ("linkedin.post",))]))
    try:
        add_to_approvals_for(context, "linkedin", "post", "A post")
        add_to_approvals_for(context, "linkedin", "comment", "A comment")  # no API for comments
        add_to_approvals_for(context, "x", "post", "An X post")  # not connected
    finally:
        registry.set_current(SenderRegistry())
    with session_scope() as s:
        kinds = [(i.platform, i.item_type, i.kind, i.action_type) for i in s.scalars(select(ApprovalItem).order_by(ApprovalItem.id))]
    assert kinds == [
        ("linkedin", "post", "api", "linkedin.post"),
        ("linkedin", "comment", "copy", None),
        ("x", "post", "copy", None),
    ]


def test_connections_are_listed(client):
    assert client.get("/api/connections").json() == [
        {"label": "LinkedIn (fake)", "action_types": list(ALL), "connected": True}
    ]


def _status_error(code):
    request = httpx.Request("POST", "https://api.example/post")
    response = httpx.Response(code, json={"error": {"message": "bad token"}}, request=request)
    return httpx.HTTPStatusError("x", request=request, response=response)


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (_status_error(400), "failed"),
        (_status_error(401), "failed"),
        (_status_error(429), "failed"),
        (_status_error(500), "unclear"),
        (_status_error(503), "unclear"),
        (httpx.ReadTimeout("slow"), "unclear"),
        (httpx.ConnectError("down"), "failed"),
    ],
    ids=["400", "401", "429", "500", "503", "timeout", "no-connection"],
)
def test_http_errors_are_failed_or_unclear(error, outcome):
    result = result_from_http_error(error, "LinkedIn")
    assert result.outcome == outcome
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 401:
        assert "bad token" in result.detail


def test_a_send_cut_off_by_a_restart_is_checked_not_resent(sender):
    item = api_item("Hello")
    with session_scope() as s:
        row = s.get(ApprovalItem, item.id)
        row.status = "approved"
        row.meta = {"approved_text": "Hello", "approved_by": "you", "attempts": 1, "sending_at": "2026-10-16T08:00:00+00:00"}
        s.add(ActionRun(key=f"approval-{item.id}-attempt-1", action_type="linkedin.post", status="running"))
    with TestClient(create_app(model_provider=lambda: (lambda n: None), senders=lambda: SenderRegistry([sender]))) as c:
        out = c.get(f"/api/approvals/{item.id}").json()
        assert out["status"] == "check_manually" and "app stopped while sending" in out["meta"]["last_error"]
        assert c.post(f"/api/approvals/{item.id}/send").status_code == 409
    assert sender.sent == [] and runs() == [(f"approval-{item.id}-attempt-1", "check_manually")]


def test_items_to_check_count_as_needing_you(client):
    item = api_item("[unclear] Hello")
    client.post(f"/api/approvals/{item.id}/approve", json={})
    assert client.get("/api/approvals/count").json() == {"waiting": 1}
    assert [i["status"] for i in client.get("/api/approvals?status=waiting").json()] == ["check_manually"]
    assert client.patch("/api/settings", json={"api_posts_per_day": 3}).json()["api_posts_per_day"] == 3
