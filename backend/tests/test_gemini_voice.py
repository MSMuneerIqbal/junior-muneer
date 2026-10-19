"""Voice messages with Gemini (Settings → Voice → Voice messages engine): Gemini hears your recordings and reads
his answers aloud in the Gemini voice; the dashboard and WhatsApp both follow the setting. OpenAI stays the default."""

import asyncio
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, chunked_answer
from junior import voice as voice_mod
from junior.config import get_settings
from junior.db import Usage, session_scope
from junior.main import create_app
from junior.settings_store import set_setting
from junior.voice import FakeVoice, GeminiVoice, TranscriptResult, to_mp3

WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 2000


class OpenAISide(FakeVoice):
    calls: list[dict] = []

    async def transcribe(self, path, model, prompt, language=None):
        self.calls.append({"job": "hear", "model": model})
        return TranscriptResult(text="openai heard you", languages=["en"], seconds=6.0)

    async def speak(self, text, model, voice, speed, instructions):
        self.calls.append({"job": "speak", "model": model, "voice": voice})
        async for chunk in super().speak(text, model, voice, speed, instructions):
            yield chunk


class GeminiSide(FakeVoice):
    calls: list[dict] = []

    async def transcribe(self, path, model, prompt, language=None):
        self.calls.append({"job": "hear", "model": model})
        return TranscriptResult(text="Gemini ne suna", languages=[], seconds=6.0)

    async def speak(self, text, model, voice, speed, instructions):
        self.calls.append({"job": "speak", "model": model, "voice": voice})
        async for chunk in super().speak(text, model, voice, speed, instructions):
            yield chunk


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model, monkeypatch):
    OpenAISide.calls, GeminiSide.calls = [], []
    monkeypatch.setattr(voice_mod, "GEMINI_VOICE", GeminiSide)
    app = create_app(model_provider=lambda: (lambda _n: model), voice=OpenAISide)
    with TestClient(app) as c:
        yield c


def upload(client):
    return client.post("/api/voice/transcribe", files={"audio": ("v.webm", WEBM, "audio/webm")}, data={"seconds": "6"})


def answer(client, model, text):
    model.enqueue(chunked_answer(text))
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": "hi"})
        while (e := ws.receive_json())["type"] not in ("done", "error"):
            pass
    return e


def test_openai_is_the_default_engine(client):
    assert client.get("/api/settings").json()["voice_engine"] == "openai"
    assert upload(client).json()["text"] == "openai heard you"
    assert OpenAISide.calls == [{"job": "hear", "model": "gpt-4o-transcribe"}] and GeminiSide.calls == []


def test_with_gemini_chosen_gemini_hears_and_the_cost_is_geminis(client):
    assert client.patch("/api/settings", json={"voice_engine": "gemini"}).status_code == 200
    got = upload(client).json()
    assert got["text"] == "Gemini ne suna"
    assert GeminiSide.calls == [{"job": "hear", "model": "gemini-2.5-flash"}] and OpenAISide.calls == []
    assert got["cost_usd"] == pytest.approx(6 / 60 * 0.0015)
    with session_scope() as s:
        used = s.scalars(select(Usage).where(Usage.agent == "transcriber")).all()[-1]
        assert used.model == "gemini-2.5-flash"


def test_with_gemini_chosen_he_speaks_in_the_gemini_voice(client, model):
    client.patch("/api/settings", json={"voice_engine": "gemini", "gemini_voice": "Kore"})
    done = answer(client, model, "Walaikum salam!")
    r = client.get(f"/api/voice/speak/{done['message_id']}.mp3")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert GeminiSide.calls == [{"job": "speak", "model": "gemini-2.5-flash-preview-tts", "voice": "Kore"}]
    with session_scope() as s:
        used = s.scalars(select(Usage).where(Usage.agent == "speaker")).all()[-1]
        assert used.model == "gemini-2.5-flash-preview-tts" and used.cost_usd > 0


def test_switching_back_to_openai_uses_openai_again(client):
    client.patch("/api/settings", json={"voice_engine": "gemini"})
    upload(client)
    client.patch("/api/settings", json={"voice_engine": "openai"})
    upload(client)
    assert [c["model"] for c in GeminiSide.calls] == ["gemini-2.5-flash"]
    assert [c["model"] for c in OpenAISide.calls] == ["gpt-4o-transcribe"]


def test_openai_voice_samples_stay_openai_whatever_the_engine(client):
    client.patch("/api/settings", json={"voice_engine": "gemini"})
    assert client.get("/api/voice/preview/ash/pakistani.mp3").status_code == 200
    assert OpenAISide.calls == [{"job": "speak", "model": "gpt-4o-mini-tts", "voice": "ash"}] and GeminiSide.calls == []


def test_unknown_engine_is_refused(client):
    assert client.patch("/api/settings", json={"voice_engine": "vapi"}).status_code == 422


def test_gemini_without_a_key_says_which_key(model, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("FAKE_AI", "false")
    get_settings.cache_clear()
    try:
        app = create_app(model_provider=lambda: (lambda _n: model), voice=OpenAISide)
        with TestClient(app) as c:
            set_setting("voice_engine", "gemini")
            r = upload(c)
            assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_whatsapp_voice_notes_follow_the_engine(client):
    from junior.voice import transcribe_bytes

    client.patch("/api/settings", json={"voice_engine": "gemini"})
    heard = asyncio.run(transcribe_bytes(client.app.state.voice, b"OggS" + b"\x00" * 500, "audio/ogg; codecs=opus"))
    assert heard["text"] == "Gemini ne suna"
    assert GeminiSide.calls[-1]["model"] == "gemini-2.5-flash"


# ---- the real Gemini client, with a pretend Google SDK ---------------------------------------


class PretendModels:
    def __init__(self):
        self.asked = []

    async def generate_content(self, model, contents, config=None):
        self.asked.append({"model": model, "contents": contents, "config": config})
        if config is None:  # hearing
            usage = NS(prompt_tokens_details=[NS(modality="MediaModality.AUDIO", token_count=150),
                                              NS(modality="MediaModality.TEXT", token_count=40)])
            return NS(text=" السلام علیکم! I'm fine. \n", usage_metadata=usage)
        pcm = b"\x00\x01" * 24000  # one second of 24 kHz audio
        return NS(candidates=[NS(content=NS(parts=[NS(inline_data=NS(data=pcm))]))])


def pretend_gemini():
    v = GeminiVoice.__new__(GeminiVoice)
    v.client = NS(aio=NS(models=PretendModels()))
    return v


def test_gemini_client_hears_a_recording(tmp_path):
    v = pretend_gemini()
    path = tmp_path / "note.ogg"
    path.write_bytes(b"OggS" + b"\x00" * 100)
    result = asyncio.run(v.transcribe(path, "gemini-2.5-flash", "Write down what Muneer says.", "ur"))
    assert result.text == "السلام علیکم! I'm fine."
    assert result.seconds == 6.0  # 150 audio tokens at 25 a second
    asked = v.client.aio.models.asked[0]
    assert asked["contents"][0].inline_data.mime_type == "audio/ogg"
    assert "Urdu script" in asked["contents"][1] and "only their words" in asked["contents"][1]


def test_gemini_client_speaks_mp3_in_the_chosen_voice():
    v = pretend_gemini()

    async def run():
        return [c async for c in v.speak("Walaikum salam! " * 150, "gemini-2.5-flash-preview-tts", "Puck", 1.0, "Warm.")]

    pieces = asyncio.run(run())
    asked = v.client.aio.models.asked
    assert len(pieces) == len(asked) == 2  # long answers go in short pieces
    assert all(p[0] == 0xFF for p in pieces)  # MP3 frames
    config = asked[0]["config"]
    assert config.response_modalities == ["AUDIO"]
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"
    assert "word for word" in asked[0]["contents"]


def test_to_mp3_makes_a_playable_mp3():
    mp3 = to_mp3(b"\x00\x00" * 24000)
    assert mp3[0] == 0xFF and (mp3[1] & 0xE0) == 0xE0 and len(mp3) > 1000


class BusyGemini(FakeVoice):
    """Gemini saying "503 high demand"."""

    async def transcribe(self, path, model, prompt, language=None):
        raise RuntimeError("503 UNAVAILABLE: This model is currently experiencing high demand.")

    async def speak(self, text, model, voice, speed, instructions):
        raise RuntimeError("503 UNAVAILABLE: This model is currently experiencing high demand.")
        yield b""


def test_when_gemini_is_busy_openai_hears_the_recording_and_its_cost_is_openais(client, monkeypatch):
    monkeypatch.setattr(voice_mod, "GEMINI_VOICE", BusyGemini)
    client.patch("/api/settings", json={"voice_engine": "gemini"})
    got = upload(client).json()
    assert got["text"] == "openai heard you"
    assert OpenAISide.calls == [{"job": "hear", "model": "gpt-4o-transcribe"}]
    assert got["cost_usd"] == pytest.approx(6 / 60 * 0.006)
    with session_scope() as s:
        assert s.scalars(select(Usage).where(Usage.agent == "transcriber")).all()[-1].model == "gpt-4o-transcribe"


def test_when_gemini_is_busy_openai_reads_the_answer_in_your_openai_voice(client, model, monkeypatch):
    monkeypatch.setattr(voice_mod, "GEMINI_VOICE", BusyGemini)
    client.patch("/api/settings", json={"voice_engine": "gemini", "tts_voice": "ash"})
    done = answer(client, model, "Walaikum salam!")
    r = client.get(f"/api/voice/speak/{done['message_id']}.mp3")
    assert r.status_code == 200 and len(r.content) > 0
    assert OpenAISide.calls == [{"job": "speak", "model": "gpt-4o-mini-tts", "voice": "ash"}]


# ---- picking the models (Settings -> Voice) ---------------------------------------------------


def test_each_engine_lists_its_models_with_notes_prices_and_defaults(client):
    got = client.get("/api/voice/models").json()
    assert got["openai"]["defaults"] == {"hear": "gpt-4o-transcribe", "speak": "gpt-4o-mini-tts"}
    assert got["gemini"]["defaults"] == {"hear": "gemini-2.5-flash", "speak": "gemini-2.5-flash-preview-tts"}
    hear = {m["model"]: m for m in got["gemini"]["hear"]}
    assert set(hear) == {"gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite"}
    assert hear["gemini-3.1-flash-lite"]["per_minute"] == 0.00075 and hear["gemini-2.5-flash"]["note"]
    assert "Paid key only" in next(m["note"] for m in got["gemini"]["speak"] if m["model"] == "gemini-2.5-pro-preview-tts")
    assert {m["model"] for m in got["openai"]["hear"]} >= {"gpt-4o-transcribe", "gpt-4o-mini-transcribe"}


def test_picked_models_are_used_and_costed(client, model):
    client.patch("/api/settings", json={"voice_engine": "gemini", "voice_hear_model": "gemini-3.1-flash-lite",
                                        "voice_speak_model": "gemini-2.5-pro-preview-tts"})
    got = upload(client).json()
    assert GeminiSide.calls[-1]["model"] == "gemini-3.1-flash-lite"
    assert got["cost_usd"] == pytest.approx(6 / 60 * 0.00075)
    done = answer(client, model, "Theek hai!")
    client.get(f"/api/voice/speak/{done['message_id']}.mp3")
    assert GeminiSide.calls[-1]["model"] == "gemini-2.5-pro-preview-tts"


def test_a_pick_from_the_other_engine_falls_back_to_this_engines_default(client):
    client.patch("/api/settings", json={"voice_engine": "openai", "voice_hear_model": "gemini-3.8-flash"})
    upload(client)
    assert OpenAISide.calls[-1]["model"] == "gpt-4o-transcribe"


def test_empty_means_default_and_unknown_models_are_refused(client):
    assert client.patch("/api/settings", json={"voice_hear_model": "whisper-9"}).status_code == 422
    assert client.patch("/api/settings", json={"voice_speak_model": "gpt-4o-transcribe"}).status_code == 422  # hears, can't speak
    assert client.patch("/api/settings", json={"voice_hear_model": "gpt-4o-mini-transcribe"}).status_code == 200
    assert client.patch("/api/settings", json={"voice_hear_model": ""}).status_code == 200
    upload(client)
    assert OpenAISide.calls[-1]["model"] == "gpt-4o-transcribe"
