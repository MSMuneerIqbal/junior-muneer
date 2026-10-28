import pytest
from fastapi.testclient import TestClient

from junior.approvals import ApprovalError, approve_item, create_item, edit_item, mark_posted
from junior.main import create_app
from junior.permissions import rule_for, set_mode, set_rule


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


def api_item(**kw):
    return create_item(kind="api", platform="linkedin", item_type="post", text="Hello LinkedIn", action_type="linkedin.post", **kw)


# --- copy-and-paste items ------------------------------------------------------


def test_copy_item_flow_and_edits_are_kept(client):
    created = client.post(
        "/api/approvals", json={"platform": "upwork", "item_type": "proposal", "text": "Hi, I can build this."}
    ).json()
    assert created["status"] == "waiting" and created["kind"] == "copy"
    assert created["open_url"].startswith("https://www.upwork.com")
    assert client.get("/api/approvals/count").json() == {"waiting": 1}

    edited = client.patch(f"/api/approvals/{created['id']}", json={"text": "Hi! I can build this in 5 days."}).json()
    assert edited["text"] == "Hi! I can build this in 5 days."
    assert edited["original_text"] == "Hi, I can build this."
    assert edited["edits"][0]["before"] == "Hi, I can build this."

    # Copy items can't be "approved": the system never sends them.
    r = client.post(f"/api/approvals/{created['id']}/approve", json={})
    assert r.status_code == 409 and "copy-and-paste" in r.json()["detail"]

    posted = client.post(f"/api/approvals/{created['id']}/posted").json()
    assert posted["status"] == "posted"
    assert client.get("/api/approvals/count").json() == {"waiting": 0}
    # Once posted, it can't be edited any more.
    assert client.patch(f"/api/approvals/{created['id']}", json={"text": "x"}).status_code == 409


def test_api_cannot_create_api_items(client):
    r = client.post("/api/approvals", json={"platform": "linkedin", "text": "hi", "action_type": "linkedin.post"})
    assert r.status_code == 201 and r.json()["kind"] == "copy" and r.json()["action_type"] is None
    assert client.post("/api/approvals", json={"platform": "myspace", "text": "hi"}).status_code == 422


def test_reject_and_restore(client):
    item = create_item(kind="copy", platform="x", item_type="post", text="Short post")
    assert client.post(f"/api/approvals/{item.id}/reject").json()["status"] == "rejected"
    assert client.get("/api/approvals?status=rejected").json()[0]["id"] == item.id
    assert client.post(f"/api/approvals/{item.id}/restore").json()["status"] == "waiting"
    assert client.post("/api/approvals/999/reject").status_code == 404


def test_comment_opens_the_post_it_answers(client):
    item = create_item(
        kind="copy", platform="linkedin", item_type="comment", text="Great point!",
        meta={"source_url": "https://www.linkedin.com/posts/someone-123"},
    )
    assert item.open_url == "https://www.linkedin.com/posts/someone-123"
    bad = create_item(kind="copy", platform="linkedin", item_type="comment", text="Hi", meta={"source_url": "javascript:alert(1)"})
    assert bad.open_url == "https://www.linkedin.com/feed/"


# --- API items follow the permission rules -------------------------------------


def test_api_item_waits_and_approve_keeps_the_exact_text(client):
    item = api_item()
    assert item.status == "waiting" and item.can_always_allow
    edit_item(item.id, "Hello LinkedIn, edited")
    approved = approve_item(item.id)
    assert approved.status == "approved"
    assert approved.meta["approved_text"] == "Hello LinkedIn, edited"
    with pytest.raises(ApprovalError):
        approve_item(item.id)  # only once
    with pytest.raises(ApprovalError):
        mark_posted(item.id)  # API items are posted by the sender, not by hand


def test_always_allow_switches_the_rule_to_auto(client):
    item = api_item()
    client.post(f"/api/approvals/{item.id}/approve", json={"always_allow": True})
    assert rule_for("linkedin.post") == "auto"
    assert api_item().status == "approved"  # the next one goes straight through


def test_auto_rule_still_asks_for_outside_content(client):
    set_rule("linkedin.post", "auto")
    item = api_item(from_outside=True)
    assert item.status == "waiting" and not item.can_always_allow
    r = client.post(f"/api/approvals/{item.id}/approve", json={"always_allow": True})
    assert r.status_code == 409
    assert client.post(f"/api/approvals/{item.id}/approve", json={}).json()["status"] == "approved"


def test_ask_everything_holds_auto_items(client):
    set_rule("linkedin.post", "auto")
    set_mode("ask_all")
    assert api_item().status == "waiting"


def test_formerly_locked_items_offer_always_allow(client):
    item = create_item(kind="api", platform="github", item_type="merge", text="Merge PR 4", action_type="github.merge")
    assert item.status == "waiting" and item.can_always_allow
    approve_item(item.id, always_allow=True)
    assert rule_for("github.merge") == "auto"


def test_deny_refuses_the_item(client):
    with pytest.raises(ApprovalError, match="Never runs"):
        create_item(kind="api", platform="github", item_type="delete", text="Delete repo", action_type="github.repo.delete")
    item = api_item()
    set_rule("linkedin.post", "deny")
    with pytest.raises(ApprovalError, match="Never runs"):
        approve_item(item.id)


# --- in the chat ------------------------------------------------------------------


def test_a_draft_from_chat_shows_as_a_card_and_stays_in_sync():
    from junior.agent.fake import fake_model_provider

    with TestClient(create_app(model_provider=fake_model_provider)) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "draft I shipped my MCP server today"})
            events = []
            while (e := ws.receive_json())["type"] not in ("done", "error"):
                events.append(e)
            done = e
        card = next(e for e in events if e["type"] == "approval")["item"]
        assert card["text"] == "I shipped my MCP server today" and card["status"] == "waiting"

        messages = c.get(f"/api/conversations/{done['conversation_id']}/messages").json()
        assert messages[-1]["approvals"][0]["id"] == card["id"]

        # Acting on the Approvals page changes the card in the chat (same item).
        c.post(f"/api/approvals/{card['id']}/posted")
        messages = c.get(f"/api/conversations/{done['conversation_id']}/messages").json()
        assert messages[-1]["approvals"][0]["status"] == "posted"
        names = [a["name"] for a in c.get("/api/activity?kind=action").json()]
        assert "approval_created" in names and "approval_posted" in names

