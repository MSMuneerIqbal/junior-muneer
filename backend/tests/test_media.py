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
    assert not is_request("dnt play the song blue eyes")
    assert not is_request("song mat chalao blue eyes")
    assert not is_request("song mat chalo blue eyes")
    assert not is_request("how do I play a song on YouTube?")
    assert not is_request("play the role of a music critic")
    assert not is_request("translate this sentence: play the song Blue Eyes")
    assert is_request("play the song Blue Eyes in my signed-in browser")
    assert matches_request("play the song Blue Eyes in my signed-in browser", "Blue Eyes Full Video Song")
    assert not is_request("play the song Blue Eyes and send an email")
    assert is_request("یار ایک سونگ تو چلا دو YouTube پہ Blue Eyes")
    assert matches_request("یار ایک سونگ تو چلا دو YouTube پہ Blue Eyes", "Blue Eyes Full Video Song")
    assert is_request("Ab change kro song chalo blue eyes")
    assert matches_request("Ab change kro song chalo dnt tell your dream to everyone body around", "Don't Tell Your Dreams - LOVIXX, STOSLIV")
    assert is_request("Song blue eyes yo yo honey Singh")
    assert not is_request("song lyrics blue eyes honey singh")
    assert not is_request("where r is song paly i dn see")
    urdu = "ایک سونگ پلے کرو یار مہک ملک کا جس کا نام ہے ایادن چن باہوں سونا ہے"
    assert is_request(urdu)
    assert matches_request(urdu, "Ay Ahdin Chan Baon Sohnra Ay | Mehak Malik | Dance Performance")
    assert not matches_request(urdu, "Dhole Nun Banda Mul Lay Le | Mehak Malik")
    assert not is_request("یہ سونگ پلے مت کرو")
    assert not is_request("یہ سونگ مت پلے کرو")
    assert is_request("مجھے مہک ملک کا نغمہ سناؤ")
    assert not is_request("مہک ملک کا نغمہ مت سناؤ")


def test_urdu_continuation_is_recognized():
    from junior.browser.media import is_continue
    assert is_continue("جاری رکھو")


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


def test_explicit_personal_browser_request_never_opens_a_separate_browser(client):
    events, result = chat(client, "play the song Blue Eyes in my signed-in browser")
    assert "Select My Chrome profile" in result["text"]
    assert not [event for event in events if event["type"] == "approval"]


def test_continuation_reports_player_error_instead_of_claiming_success(client):
    _, result = chat(client, "play the song blue eyes honey singh")
    player = client.app.state.media_player
    player.problem = "YouTube stopped playback with a player error. The player is still open; check it before trying again."
    assert client.get("/api/computer/media").json()["playback_error"] == player.problem
    events, answer = chat(client, "continue", result["conversation_id"])
    assert "stopped playback" in answer["text"]
    assert not [event for event in events if event["type"] == "approval"]


def test_player_reports_visible_error_and_recovers_after_playback_resumes():
    import asyncio
    from junior.browser.media import Player

    class Page:
        def __init__(self):
            self.state = {"error": True, "playing": False}
        async def evaluate(self, script):
            return self.state

    player = Player()
    player.page = Page()
    asyncio.run(player.check_playback())
    assert "stopped playback" in player.problem
    player.page.state = {"error": False, "playing": True}
    asyncio.run(player.check_playback())
    assert player.problem == ""


def test_change_song_auto_and_manual_and_session_guard(client):
    _, played = chat(client, "play the song blue eyes honey singh")
    conversation = played["conversation_id"]
    events, result = chat(client, "song change kro", conversation)
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["action_type"] == "computer.media.change" and card["status"] == "posted"
    assert "Simulated changing" in result["text"]
    set_mode("ask_all")
    events, _ = chat(client, "change it", conversation)
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["status"] == "waiting"
    set_mode("rules")
    chat(client, "play the song blue eyes again", conversation)
    result = client.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert result["status"] != "posted" and "player changed" in result["meta"]["last_error"]


def test_change_request_does_not_guess_a_named_song():
    from junior.browser.media import is_change_request
    assert is_change_request("next song") and is_change_request("change it")
    assert not is_change_request("do not change the song")
    assert not is_change_request("change song to blue eyes")


def test_change_song_uses_independent_whatsapp_manual_mode(client):
    from junior.permissions import ACTION_CHANNEL, decide
    from junior.settings_store import set_setting
    set_mode("rules")
    set_setting("whatsapp_action_mode", "ask_all")
    token = ACTION_CHANNEL.set("whatsapp")
    try:
        assert decide("computer.media.change", from_outside=False).rule == "ask"
    finally:
        ACTION_CHANNEL.reset(token)


def test_next_song_uses_only_valid_youtube_recommendation():
    import asyncio
    from junior.browser.media import BrowserRefused, Player

    class Locator:
        first = None
        def __init__(self, href):
            self.href = href
            self.first = self
        async def get_attribute(self, name):
            return self.href

    class Page:
        def __init__(self, href):
            self.href = href
            self.visited = []
        def is_closed(self):
            return False
        def locator(self, selector):
            return Locator(self.href)
        async def goto(self, url, **kwargs):
            self.visited.append(url)
        async def wait_for_function(self, script, **kwargs):
            pass

    player = Player()
    player.page = Page("https://evil.example/watch?v=fakevideo01")
    player.video_id, player.session = "oldvideo001", "original"
    with pytest.raises(BrowserRefused):
        asyncio.run(player.next())
    assert player.page.visited == [] and player.session == "original"
    player.page.href = "/watch?v=fakevideo01&list=other"
    asyncio.run(player.next())
    assert player.page.visited == ["https://www.youtube.com/watch?v=fakevideo01"]
    assert player.video_id == "fakevideo01" and player.session != "original"


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


def test_waiting_play_card_cannot_switch_to_another_browser(client):
    from junior.settings_store import set_setting
    set_mode("ask_all")
    events, _ = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    set_setting("signed_browser_media", True)
    result = client.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert result["status"] != "posted"
    assert not client.app.state.media_player.session


def test_waiting_signed_play_card_cannot_use_a_new_connection(client):
    from junior.settings_store import set_setting
    class Peer:
        async def close(self, **kwargs):
            pass
    bridge = client.app.state.signed_browser
    bridge.socket = Peer()
    set_setting("signed_browser_media", True)
    set_mode("ask_all")
    events, _ = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    bridge.generation = "new-connection"
    result = client.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert result["status"] != "posted"
    assert not client.app.state.media_player.session


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
    async def require_verification(payload, **kwargs):
        raise VerificationRequired("YouTube requested verification. Complete it in the visible player; playback is not confirmed.")
    monkeypatch.setattr(client.app.state.media_player, "play", require_verification)
    events, result = chat(client, "play the song blue eyes honey singh")
    card = next(event["item"] for event in events if event["type"] == "approval")
    assert card["status"] == "check_manually" and "verification" in result["text"]
    events, _ = chat(client, "continue", result["conversation_id"])
    assert not [event for event in events if event["type"] == "approval"]
