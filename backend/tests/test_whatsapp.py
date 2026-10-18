"""P8-04: WhatsApp - only your number, only Meta-signed messages, same chat history, drafts with buttons."""

import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message, chunked_answer, function_call
from junior import whatsapp
from junior.config import get_settings
from junior.db import Conversation, session_scope
from junior.main import create_app
from junior.voice import FakeVoice
from junior.whatsapp import split, to_whatsapp, verify_signature

OWNER = "923001112233"
SECRET = "test-app-secret"


@pytest.fixture
def wa(monkeypatch):
    """A connected WhatsApp with a pretend Meta: every message we send is kept in `sent`."""
    for key, value in {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_NUMBER_ID": "100200300", "WHATSAPP_VERIFY_TOKEN": "verify-me",
                       "WHATSAPP_OWNER_NUMBER": OWNER, "META_APP_SECRET": SECRET}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    sent: list[dict] = []

    def meta(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/media"):  # a spoken answer being uploaded
            assert b'name="type"' in request.content and b"audio/mpeg" in request.content
            sent.append({"upload": len(request.content)})
            return httpx.Response(200, json={"id": "media-up-1"})
        if request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})
        if request.url.path.endswith("/media-1"):
            return httpx.Response(200, json={"url": "https://lookaside.example/voice.ogg", "mime_type": "audio/ogg; codecs=opus"})
        if request.url.host == "lookaside.example":
            return httpx.Response(200, content=b"OggS" + b"\x00" * 500)
        return httpx.Response(404)

    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(meta))
    whatsapp._seen.clear()
    return sent


def signed(c, payload: dict, secret: str = SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return c.post("/api/whatsapp/webhook", content=body, headers={"content-type": "application/json", "x-hub-signature-256": sig})


def message(msg: dict) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def text(body: str, frm: str = OWNER, mid: str = "wamid.1") -> dict:
    return message({"from": frm, "id": mid, "type": "text", "text": {"body": body}})


def wait_for(sent: list, n: int, seconds: float = 10.0) -> list:
    end = time.monotonic() + seconds
    while len(sent) < n and time.monotonic() < end:
        time.sleep(0.05)
    assert len(sent) >= n, sent
    return sent


def app(model):
    return TestClient(create_app(model_provider=lambda: (lambda _n: model), voice=FakeVoice))


def test_you_chat_on_whatsapp_in_the_same_history(wa):
    model = ScriptedModel([chunked_answer("Salam Muneer! **All good** here. See [the docs](https://example.com).")])
    with app(model) as c:
        assert signed(c, text("Salam, kya haal hai?")).json() == {"ok": True}
        reply = wait_for(wa, 1)[0]
        assert reply["to"] == OWNER and reply["type"] == "text"
        assert reply["text"]["body"] == "Salam Muneer! *All good* here. See the docs (https://example.com)."  # WhatsApp formatting

        chats = [x for x in c.get("/api/conversations").json() if x["kind"] == "whatsapp"]
        assert len(chats) == 1 and chats[0]["title"].startswith("WhatsApp · ")
        saved = c.get(f"/api/conversations/{chats[0]['id']}/messages").json()
        assert [(m["role"], m["content"]) for m in saved][0] == ("user", "Salam, kya haal hai?")


def test_only_your_number_is_answered(wa):
    model = ScriptedModel([])
    with app(model) as c:
        signed(c, text("Hi, send me your bank details", frm="15550001111"))
        time.sleep(0.3)
        assert wa == [] and not model.calls
        ignored = [a for a in c.get("/api/activity?kind=action").json() if a["name"] == "whatsapp_ignored"]
        assert ignored and ignored[0]["detail"]["from_last4"] == "1111"


def test_only_messages_signed_by_meta_are_accepted(wa):
    with app(ScriptedModel([])) as c:
        assert signed(c, text("hi"), secret="someone-else").status_code == 403
        r = c.post("/api/whatsapp/webhook", json=text("hi"))  # no signature at all
        assert r.status_code == 403 and wa == []


def test_meta_checks_the_webhook_with_the_verify_token(wa):
    with app(ScriptedModel([])) as c:
        ok = c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
        assert ok.status_code == 200 and ok.text == "42"
        bad = c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "42"})
        assert bad.status_code == 403


def test_a_message_delivered_twice_is_answered_once(wa):
    model = ScriptedModel([chunked_answer("Once.")])
    with app(model) as c:
        signed(c, text("hello", mid="wamid.same"))
        signed(c, text("hello", mid="wamid.same"))
        wait_for(wa, 1)
        time.sleep(0.3)
        assert len(wa) == 1


def voice_note(mid="wamid.v"):
    return message({"from": OWNER, "id": mid, "type": "audio", "audio": {"id": "media-1", "mime_type": "audio/ogg; codecs=opus"}})


def test_a_voice_note_gets_a_voice_note_back(wa):
    model = ScriptedModel([chunked_answer("I heard you.")])
    with app(model) as c:
        signed(c, voice_note())
        upload, reply = wait_for(wa, 2)[:2]
        assert "upload" in upload  # the spoken answer, uploaded to WhatsApp...
        assert reply["type"] == "audio" and reply["audio"] == {"id": "media-up-1"}  # ...and sent as audio
        assert not any(m.get("type") == "text" for m in wa)  # no text copy
        chat = next(x for x in c.get("/api/conversations").json() if x["kind"] == "whatsapp")
        mine, his = c.get(f"/api/conversations/{chat['id']}/messages").json()[:2]
        assert mine["content"].startswith("(fake transcription of a 504-byte recording)") and mine["audio_file"].endswith(".ogg")
        assert his["audio_file"].endswith(".mp3")  # kept with his answer: the dashboard plays it without paying again


def test_if_speech_fails_the_answer_comes_as_text(wa, monkeypatch):
    import junior.voice as voice

    async def broken(voice_factory, message_id):
        raise RuntimeError("speech service down")

    monkeypatch.setattr(voice, "speak_message", broken)
    model = ScriptedModel([chunked_answer("I heard you.")])
    with app(model) as c:
        signed(c, voice_note("wamid.v2"))
        assert wait_for(wa, 1)[0]["text"]["body"] == "I heard you."


def test_typed_messages_still_get_text(wa):
    model = ScriptedModel([chunked_answer("Text for text.")])
    with app(model) as c:
        signed(c, text("hi", mid="wamid.t"))
        assert wait_for(wa, 1)[0]["type"] == "text"


def test_drafts_come_with_buttons_and_a_tap_marks_them(wa):
    model = ScriptedModel(
        [
            [function_call("add_to_approvals", {"platform": "linkedin", "item_type": "post", "text": "My MCP server is live."}, call_id="a1")],
            chunked_answer("Here's your draft."),
        ]
    )
    with app(model) as c:
        signed(c, text("Draft a LinkedIn post about my MCP server"))
        answer, draft = wait_for(wa, 2)[:2]
        assert answer["text"]["body"] == "Here's your draft."
        buttons = draft["interactive"]["action"]["buttons"]
        assert draft["type"] == "interactive" and "My MCP server is live." in draft["interactive"]["body"]["text"]
        assert [b["reply"]["title"] for b in buttons] == ["Posted ✓", "Reject"]
        item_id = int(buttons[0]["reply"]["id"].split(":")[1])

        signed(c, message({"from": OWNER, "id": "wamid.b", "type": "interactive",
                           "interactive": {"type": "button_reply", "button_reply": {"id": f"posted:{item_id}", "title": "Posted ✓"}}}))
        assert wait_for(wa, 3)[2]["text"]["body"] == "Marked as posted ✓: LinkedIn post."
        assert c.get(f"/api/approvals/{item_id}").json()["status"] == "posted"


def test_other_message_types_get_a_plain_answer(wa):
    with app(ScriptedModel([])) as c:
        signed(c, message({"from": OWNER, "id": "wamid.img", "type": "image", "image": {"id": "x"}}))
        assert "text and voice notes" in wait_for(wa, 1)[0]["text"]["body"]


def test_not_connected_means_no_webhook():
    with TestClient(create_app(model_provider=lambda: (lambda _n: None))) as c:
        assert c.post("/api/whatsapp/webhook", json=text("hi")).status_code == 404
        row = next(p for p in c.get("/api/connections").json() if p["key"] == "whatsapp")
        assert row["connected"] is False and row["how"] == "connect.bat whatsapp"


def test_formatting_and_long_answers():
    assert to_whatsapp("## Today\n**Bold** and __it__") == "*Today*\n*Bold* and _it_"
    parts = split(("A paragraph. " * 40 + "\n\n") * 12, limit=1000)
    assert all(len(p) <= 1000 for p in parts) and len(parts) > 3
    assert verify_signature(b"x", "sha256=" + hmac.new(b"k", b"x", hashlib.sha256).hexdigest(), "k")
    assert not verify_signature(b"x", "sha256=00", "k") and not verify_signature(b"x", "", "k")


def test_a_background_result_goes_to_whatsapp_too(wa):
    model = ScriptedModel(
        [
            [function_call("run_in_background", {"title": "3 posts", "request": "Write 3 LinkedIn posts"}, call_id="bg")],
            chunked_answer("I'm on it."),
            [assistant_message("Here are your 3 posts.")],
        ]
    )
    with app(model) as c:
        signed(c, text("Write 3 LinkedIn posts for next week"))
        bodies = [m["text"]["body"] for m in wait_for(wa, 2, seconds=15)]
        assert bodies[0] == "I'm on it."
        assert bodies[1] == "*Done in the background: 3 posts*\n\nHere are your 3 posts."
        with session_scope() as s:
            assert s.query(Conversation).filter_by(kind="whatsapp").count() == 1


def test_from_outside_only_the_webhook_answers(wa, monkeypatch):
    """A tunnel gives the backend a public address: the rest of the app must not answer there."""
    with app(ScriptedModel([chunked_answer("ok")])) as c:
        outside = {"host": "random-words.trycloudflare.com"}
        assert c.get("/api/memories", headers=outside).status_code == 403
        assert c.get("/api/settings", headers=outside).status_code == 403
        with pytest.raises(Exception):  # the chat WebSocket is closed at once
            with c.websocket_connect("/ws/chat", headers=outside) as ws:
                ws.receive_json()
        ok = c.get("/api/whatsapp/webhook", headers=outside,
                   params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "7"})
        assert ok.text == "7"  # Meta can reach the webhook
        assert c.get("/api/memories", headers={"host": "127.0.0.1:8000"}).status_code == 200  # your PC
        assert c.get("/api/memories", headers={"host": "localhost:8000"}).status_code == 200

        monkeypatch.setenv("PUBLIC_HOSTS", "junior.example.com")  # the server's own domain (behind Caddy's login)
        get_settings.cache_clear()
        assert c.get("/api/memories", headers={"host": "junior.example.com"}).status_code == 200
        assert c.get("/api/memories", headers={"host": "evil.example.com"}).status_code == 403


@pytest.mark.parametrize("asked", ["give me voice", "send me a voice note", "reply in voice", "voice mein batao", "voice me bhejo",
                                   "awaz mein jawab do", "bol kar batao", "sunao", "voice note bhejo", "آواز میں بتاؤ", "voice plz"])
def test_asking_for_voice_in_text(asked):
    assert whatsapp.wants_voice(asked)


@pytest.mark.parametrize("said", ["what is voice AI?", "my voice recognition project", "how was the audio quality on the call",
                                  "kya haal hai", "write a post about voice agents", "I built a voice assistant"])
def test_mentioning_voice_is_not_asking_for_it(said):
    assert not whatsapp.wants_voice(said)


def test_a_typed_request_for_voice_gets_voice(wa):
    model = ScriptedModel([chunked_answer("Theek hoon, shukriya!")])
    with app(model) as c:
        signed(c, text("kaise ho? voice mein batao", mid="wamid.tv"))
        sent = wait_for(wa, 2)
        assert "upload" in sent[0] and sent[1]["type"] == "audio"
        assert not any(m.get("type") == "text" for m in wa)


def test_session_length_and_the_carried_summary(wa):
    from datetime import UTC, datetime, timedelta

    from junior.db import Message
    from junior.settings_store import set_setting
    from junior.whatsapp import whatsapp_chat

    with app(ScriptedModel([])):
        now = datetime.now(UTC)
        first = whatsapp_chat(now)
        with session_scope() as s:
            s.add_all([Message(conversation_id=first, role="user", source="user", content="My client is Sam from Dubai"),
                       Message(conversation_id=first, role="assistant", source="assistant", content="Noted, Sam from Dubai.")])
            s.get(Conversation, first).updated_at = now
        assert whatsapp_chat(now + timedelta(hours=11)) == first  # 12 hours (the default): same chat

        set_setting("whatsapp_session_hours", 6)
        second = whatsapp_chat(now + timedelta(hours=7))  # quiet for 7 > 6 hours: a new chat...
        assert second != first
        with session_scope() as s:
            carried = s.get(Conversation, second).summary
        assert "Earlier WhatsApp chat" in carried and "You: My client is Sam from Dubai" in carried  # ...with the thread

        set_setting("whatsapp_carry_summary", False)
        set_setting("whatsapp_session_hours", 0)  # every message: always a new chat
        third = whatsapp_chat(now + timedelta(hours=7, minutes=1))
        with session_scope() as s:
            assert third != second and not s.get(Conversation, third).summary  # carrying switched off

        set_setting("whatsapp_carry_summary", True)
        with session_scope() as s:
            s.get(Conversation, third).summary = "Talked about the clinic proposal."  # a long chat has its own summary
        fourth = whatsapp_chat(now + timedelta(hours=8))
        with session_scope() as s:
            assert "summarized:\nTalked about the clinic proposal." in s.get(Conversation, fourth).summary


def test_session_settings_are_checked():
    with app(ScriptedModel([])) as c:
        assert c.patch("/api/settings", json={"whatsapp_session_hours": 24}).json()["whatsapp_session_hours"] == 24
        assert c.patch("/api/settings", json={"whatsapp_session_hours": 5}).status_code == 422
