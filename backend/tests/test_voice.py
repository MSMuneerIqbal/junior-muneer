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
    languages: list = []

    async def transcribe(self, path, model, prompt, language=None):
        self.prompts.append(prompt)
        self.languages.append(language)
        return TranscriptResult(text="Assalam o alaikum, kaise ho?", languages=["ur"], seconds=6.0)


class HindiFirstVoice(FakeVoice):
    """Hears Urdu as Hindi unless told the language is Urdu."""

    languages: list = []

    async def transcribe(self, path, model, prompt, language=None):
        self.languages.append(language)
        if language == "ur":
            return TranscriptResult(text="آپ کیسے ہیں؟", languages=["ur"], seconds=3.0)
        return TranscriptResult(text="आप कैसे हैं?", languages=["hi"], seconds=3.0)


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
    # gpt-4o-transcribe: $0.006 per minute
    assert body["cost_usd"] == pytest.approx(6 / 60 * 0.006)

    # Saved and playable.
    played = client.get(f"/api/audio/{body['audio_id']}")
    assert played.status_code == 200 and played.content == WEBM
    assert played.headers["content-type"].startswith("audio/webm")

    with session_scope() as s:
        row = s.scalars(select(Usage)).one()
        assert (row.agent, row.mode, row.model) == ("transcriber", "voice", "gpt-4o-transcribe")
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


def test_urdu_heard_as_hindi_is_transcribed_again_as_urdu(model):
    HindiFirstVoice.languages = []
    app = create_app(model_provider=lambda: (lambda _n: model), voice=HindiFirstVoice)
    with TestClient(app) as client:
        body = upload(client).json()
        assert body["text"] == "آپ کیسے ہیں؟"
        assert HindiFirstVoice.languages == [None, "ur"]
        assert body["seconds"] == 6.0  # both runs are billed
        row = client.get("/api/activity?kind=tool_call").json()[0]
        assert row["detail"]["retried_as_urdu"] is True


def test_urdu_language_setting_forces_urdu(client):
    RecordingVoice.languages = []
    set_setting("language", "urdu")
    upload(client)
    assert RecordingVoice.languages == ["ur"]


def test_prompt_asks_for_urdu_script(client):
    upload(client)
    assert "never translate" in RecordingVoice.prompts[-1]
    assert "Write Urdu in Urdu script" in RecordingVoice.prompts[-1]
    # No example sentences: on noise the model would write them out as fake messages.
    assert not any("؀" <= ch <= "ۿ" for ch in RecordingVoice.prompts[-1])


class NoiseVoice(FakeVoice):
    async def transcribe(self, path, model, prompt, language=None):
        return TranscriptResult(
            text="السلام علیکم", languages=["ur"], seconds=2.0,
            logprobs=[{"token": "x", "logprob": -2.4}],
        )


def test_a_recording_of_just_breathing_sends_nothing(model):
    app = create_app(model_provider=lambda: (lambda _n: model), voice=NoiseVoice)
    with TestClient(app) as client:
        body = upload(client).json()
    assert body["text"] == ""  # the dashboard says "I didn't catch that"


def test_noise_detection():
    from junior.voice import is_noise

    assert is_noise("", None)
    assert is_noise(" . ", None)
    assert is_noise("ہاں", [{"logprob": -2.2}])
    assert not is_noise("آپ کیسے ہیں؟", [{"logprob": -0.05}, {"logprob": -0.2}])
    assert not is_noise("Hello", None)  # no scores (older models): keep it
