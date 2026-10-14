"""Spoken replies (text-to-speech)."""

import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer
from junior.main import create_app
from junior.settings_store import set_setting
from junior.voice import FakeVoice, chunks, speakable


class RecordingVoice(FakeVoice):
    calls: list[dict] = []

    async def speak(self, text, model, voice, speed, instructions):
        self.calls.append({"text": text, "model": model, "voice": voice, "speed": speed})
        async for chunk in super().speak(text, model, voice, speed, instructions):
            yield chunk


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    RecordingVoice.calls = []
    app = create_app(model_provider=lambda: (lambda _n: model), voice=RecordingVoice)
    with TestClient(app) as c:
        yield c


def answer(client, model, text):
    model.enqueue(chunked_answer(text))
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": "hi"})
        while (e := ws.receive_json())["type"] not in ("done", "error"):
            pass
    return e


def speak(client, message_id):
    return client.get(f"/api/voice/speak/{message_id}.mp3")


def test_speak_streams_audio_once_then_reuses_it(client, model):
    done = answer(client, model, "**Hello** Muneer! See [Dawn](https://dawn.com).")
    first = speak(client, done["message_id"])
    assert first.status_code == 200 and first.headers["content-type"] == "audio/mpeg"
    assert first.content.startswith(bytes([0xFF, 0xFB])) and len(first.content) == 404
    assert RecordingVoice.calls[0]["text"] == "Hello Muneer! See Dawn."  # no markdown, no URL
    assert RecordingVoice.calls[0]["model"] == "gpt-4o-mini-tts"

    again = speak(client, done["message_id"])
    assert again.content == first.content
    assert len(RecordingVoice.calls) == 1  # saved, not paid for twice

    messages = client.get(f"/api/conversations/{done['conversation_id']}/messages").json()
    assert messages[1]["audio_file"].endswith(".mp3")
    assert client.get("/api/usage/today").json()["by_agent"]["speaker"] > 0
    names = [r["name"] for r in client.get("/api/activity?kind=tool_call").json()]
    assert names.count("speak") == 1


def test_two_requests_at_once_make_it_only_once(client, model):
    import concurrent.futures

    done = answer(client, model, "Hi there")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: speak(client, done["message_id"]), range(2)))
    assert all(r.status_code == 200 and len(r.content) == 404 for r in results)
    assert len(RecordingVoice.calls) == 1


def test_a_failed_speech_is_not_saved(client, model, monkeypatch):
    async def broken(self, *args):
        yield b"partial"
        raise RuntimeError("TTS down")

    monkeypatch.setattr(RecordingVoice, "speak", broken)
    done = answer(client, model, "Hi")
    speak(client, done["message_id"])
    messages = client.get(f"/api/conversations/{done['conversation_id']}/messages").json()
    assert messages[1]["audio_file"] is None  # will be tried again next time
    rows = client.get("/api/activity?kind=tool_call").json()
    assert rows[0]["name"] == "speak" and rows[0]["result"] == "error"


def test_uses_your_voice_and_speed(client, model):
    set_setting("tts_voice", "cedar")
    set_setting("tts_speed", 1.25)
    done = answer(client, model, "Hi")
    speak(client, done["message_id"])
    assert RecordingVoice.calls[0]["voice"] == "cedar" and RecordingVoice.calls[0]["speed"] == 1.25


def test_only_his_answers_can_be_spoken(client, model):
    done = answer(client, model, "Hi")
    assert speak(client, done["message_id"] - 1).status_code == 404  # your own message
    assert speak(client, 999).status_code == 404


def test_cap_blocks_speaking(client, model):
    done = answer(client, model, "Hi")
    set_setting("daily_cap_usd", 0.0)
    r = speak(client, done["message_id"])
    assert r.status_code == 429 and "Daily safety cap" in r.json()["detail"]


def test_voice_settings_are_checked(client):
    assert client.patch("/api/settings", json={"tts_voice": "robot"}).status_code == 422
    assert client.patch("/api/settings", json={"tts_speed": 5}).status_code == 422
    ok = client.patch("/api/settings", json={"tts_voice": "nova", "voice_autoplay": False}).json()
    assert ok["tts_voice"] == "nova" and ok["voice_autoplay"] is False
    assert "marin" in client.get("/api/voices").json()


def test_speakable_reads_well():
    md = "## Plan\n- **Morning:** write\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```py\nx=1\n```\nآج کیا ہے؟"
    assert speakable(md) == "Plan\nMorning: write\n\na, b\n\n1, 2\n\n (code shown on screen) \nآج کیا ہے؟"


def test_long_answers_are_split_under_the_limit():
    parts = chunks("Hello there. " * 700)
    assert len(parts) == 3 and all(len(p) <= 4000 for p in parts)
    assert chunks("آج کیا ہے؟ کل کیا ہوگا؟", limit=12) == ["آج کیا ہے؟", "کل کیا ہوگا؟"]
