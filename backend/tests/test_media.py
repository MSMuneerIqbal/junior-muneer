import json

import pytest
from fastapi.testclient import TestClient

from junior.browser.media import is_request, matches_request
from junior.config import get_settings
from junior.main import create_app
from junior.permissions import set_mode, set_rule


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FAKE_AI", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        client.put("/api/computer/browser", json={"enabled": True, "sites": ["*"]})
        yield client
    get_settings.cache_clear()


def chat(client, text, conversation_id=None):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": conversation_id, "text": text})
        events = []
        while (event := ws.receive_json())["type"] not in ("done", "error"):
            events.append(event)
        return events, event


def test_song_request_matching_is_specific():
    request = "song play kro yr blue eyes yo yo honey sing wala"
    assert is_request(request)
    assert matches_request(request, "Blue Eyes Full Video Song Yo Yo Honey Singh")
    assert not matches_request(request, "A totally unrelated documentary")
    assert not is_request("write an essay about the history of music")
    assert not is_request("do not play the song blue eyes")
    assert not is_request("song mat chalao blue eyes")
    assert not is_request("how do I play a song on YouTube?")
    assert not is_request("play the role of a music critic")
    assert not is_request("translate this sentence: play the song Blue Eyes")
    assert not is_request("play the song Blue Eyes in my signed-in browser")
    assert not is_request("play the song Blue Eyes and send an email")


def test_auto_song_request_runs_one_action_without_model_or_approval(client):
    events, result = chat(client, "song play kro yr blue eyes yo yo honey sing wala")
    cards = [event["item"] for event in events if event["type"] == "approval"]
    assert result["type"] == "done" and result["cost_usd"] == 0
    assert "Simulated playback" in result["text"]
    assert len(cards) == 1 and cards[0]["status"] == "posted"
    assert cards[0]["action_type"] == "computer.media.play"
    assert client.get("/api/computer/media").json()["active"]
    stop_events, stop = chat(client, "stop the song", result["conversation_id"])
    stop_cards = [event["item"] for event in stop_events if event["type"] == "approval"]
    assert len(stop_cards) == 1 and stop_cards[0]["status"] == "posted"
    assert "Stopped Junior's YouTube player" in stop["text"]
    assert not client.app.state.media_player.session
    assert not client.get("/api/computer/media").json()["active"]


def test_manual_stop_does_not_close_a_newer_player(client):
    _, first = chat(client, "play the song blue eyes honey singh")
    set_mode("ask_all")
    events, _ = chat(client, "stop the song", first["conversation_id"])
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["status"] == "waiting"
    set_mode("rules")
    chat(client, "play the song blue eyes again", first["conversation_id"])
    newer = client.app.state.media_player.session
    result = client.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert result["status"] != "posted" and "player changed" in result["meta"]["last_error"]
    assert client.app.state.media_player.session == newer


def test_manual_song_approval_plays_without_continue(client):
    set_mode("ask_all")
    events, result = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["status"] == "waiting" and "Approve it once" in result["text"]
    done = client.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert done["status"] == "posted" and "Simulated playback" in done["meta"]["result"]
    assert client.post(f"/api/approvals/{card['id']}/approve", json={}).status_code == 409
    more, result = chat(client, "continue", result["conversation_id"])
    assert not [event for event in more if event["type"] == "approval"]
    assert "already started" in result["text"]


def test_continue_after_old_song_request_prepares_only_one_card(client):
    from junior.db import Conversation, Message, session_scope
    set_mode("ask_all")
    with session_scope() as session:
        conversation = Conversation(title="music")
        session.add(conversation)
        session.flush()
        session.add(Message(conversation_id=conversation.id, role="user", source="user",
                            content="song play kro yr blue eyes yo yo honey sing wala"))
        conversation_id = conversation.id
    events, result = chat(client, "conitnue", conversation_id)
    cards = [event["item"] for event in events if event["type"] == "approval"]
    assert len(cards) == 1 and cards[0]["status"] == "waiting"
    events, result = chat(client, "continue", conversation_id)
    assert not [event for event in events if event["type"] == "approval"]
    assert "already on an approval card" in result["text"]


@pytest.mark.parametrize("rule", ["deny", "ask"])
def test_browser_rule_still_controls_music(client, rule):
    set_rule("computer.browser.input", rule)
    events, result = chat(client, "play the song blue eyes honey singh")
    cards = [event["item"] for event in events if event["type"] == "approval"]
    if rule == "deny":
        assert not cards and "NOT done" in result["text"]
    else:
        assert len(cards) == 1 and cards[0]["status"] == "waiting"


def test_approval_rechecks_original_user_request(client):
    from junior.db import ApprovalItem, session_scope
    from junior.senders.guard import check
    set_mode("ask_all")
    events, _ = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    with session_scope() as session:
        item = session.get(ApprovalItem, card["id"])
        item.status = "approved"
        item.meta = {**item.meta, "approved_by": "you", "approved_text": item.text,
                     "media_user_message_id": -1}
        assert any("original user request" in problem for problem in check(item, item.text))


def test_verification_is_reported_and_never_replayed(client, monkeypatch):
    from junior.browser.media import VerificationRequired
    async def require_verification(payload):
        raise VerificationRequired("YouTube requested verification. Complete it in the visible player; playback is not confirmed.")
    monkeypatch.setattr(client.app.state.media_player, "play", require_verification)
    events, result = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["status"] == "check_manually" and "verification" in result["text"]
    events, _ = chat(client, "continue", result["conversation_id"])
    assert not [event for event in events if event["type"] == "approval"]
