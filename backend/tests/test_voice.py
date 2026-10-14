"""Voice messages: upload, speech-to-text, cost, saved audio, chat flow."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, chunked_answer
from junior import voice as voice_mod
from junior.db import Usage, session_scope
from junior.main import create_app
from junior.settings_store import set_setting
from junior.voice import FakeVoice, TranscriptResult

WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 2000  # looks enough like a recording for the fake


class RecordingVoice(FakeVoice):
    """Fake that reports a duration and remembers the prompt it got."""

    prompts: list[str] = []

    async def transcribe(self, path, model, prompt):
        self.prompts.append(prompt)
        return TranscriptResult(text="Assalam o alaikum, kaise ho?", languages=["ur"], seconds=6.0)


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    app = create_app(model_provider=lambda: (lambda _n: model), voice=RecordingVoice)
    with TestClient(app) as c:
        yield c


def upload(client, data=WEBM, content_type="audio/webm;codecs=opus", seconds="5.5"):
    return client.post(
        "/api/voice/transcribe",
        files={"audio": ("voice.webm", data, content_type)},
        data={"seconds": seconds},
    )


def chat(client, payload):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, **payload})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def test_transcribe_saves_the_recording_and_costs_per_minute(client):
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Assalam o alaikum, kaise ho?"
    assert body["languages"] == ["ur"]
    assert body["seconds"] == 6.0  # the API's duration wins over the browser's guess
    # gpt-transcribe: $0.0045 per minute
    assert body["cost_usd"] == pytest.approx(6 / 60 * 0.0045)

    # Saved and playable.
    played = client.get(f"/api/audio/{body['audio_id']}")
    assert played.status_code == 200 and played.content == WEBM
    assert played.headers["content-type"].startswith("audio/webm")

    with session_scope() as s:
        row = s.scalars(select(Usage)).one()
        assert (row.agent, row.mode, row.model) == ("transcriber", "voice", "gpt-transcribe")
    assert client.get("/api/usage/today").json()["by_mode"]["voice"] > 0


def test_your_name_goes_into_the_transcription_hint(client):
    set_setting("user_name", "Ali")
    upload(client)
    assert "The speaker is Ali" in RecordingVoice.prompts[-1]


def test_voice_message_goes_through_the_normal_chat(client, model):
    audio_id = upload(client).json()["audio_id"]
    model.enqueue(chunked_answer("Wa alaikum assalam! Main theek hoon."))
    events = chat(
        client, {"text": "Assalam o alaikum, kaise ho?", "audio_id": audio_id, "audio_seconds": 6}
    )
    assert events[-1]["type"] == "done"
    convo_id = events[0]["id"]

    convo = next(c for c in client.get("/api/conversations").json() if c["id"] == convo_id)
    assert convo["kind"] == "voice"  # shows with a 🎙 in the sidebar
    user_msg = client.get(f"/api/conversations/{convo_id}/messages").json()[0]
    assert user_msg["audio_file"] == audio_id and user_msg["audio_seconds"] == 6
    assert user_msg["source"] == "user"  # your own words: memory may use them
    assert model.last_call.input[-1]["content"] == "Assalam o alaikum, kaise ho?"


def test_unknown_recording_is_refused(client):
    events = chat(client, {"text": "hi", "audio_id": "0" * 32 + ".webm"})
    assert events[-1]["type"] == "error" and "recording wasn't found" in events[-1]["message"]


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"content_type": "video/mp4"}, 415),
        ({"data": b""}, 400),
    ],
)
def test_bad_uploads(client, kwargs, status):
    assert upload(client, **kwargs).status_code == status


def test_too_big(client, monkeypatch):
    monkeypatch.setattr(voice_mod, "MAX_UPLOAD_BYTES", 100)
    assert upload(client).status_code == 413


def test_cap_blocks_transcription(client):
    set_setting("daily_cap_usd", 0.0)
    r = upload(client)
    assert r.status_code == 429 and "Daily safety cap" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["../junior.db", "x.webm", "a" * 32 + ".exe"])
def test_audio_path_cannot_escape_the_folder(client, bad):
    assert client.get(f"/api/audio/{bad}").status_code == 404
