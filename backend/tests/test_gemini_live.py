"""Live calls with Gemini Live: the browser streams PCM to /ws/call/gemini, the backend relays to Gemini, runs
Junior's tools, saves the chat and counts the cost. OpenAI Realtime calls are untouched."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from junior import gemini_live
from junior.config import get_settings
from junior.db import Memory, Message, Usage, session_scope
from junior.gemini_live import URDISH_INSTRUCTION, session_config, turn_cost
from junior.main import create_app
from junior.settings_store import set_setting

AUDIO = [NS(modality="AUDIO", token_count=1000)]
TEXT = [NS(modality="TEXT", token_count=200)]


def turn(heard="", said="", audio=b"", done=True, usage=True):
    """One Gemini message per piece, like the real stream."""
    out = []
    if heard:
        out.append(NS(server_content=NS(input_transcription=NS(text=heard), output_transcription=None, model_turn=None,
                                        interrupted=False, turn_complete=False), usage_metadata=None, tool_call=None))
    if said or audio:
        out.append(NS(server_content=NS(input_transcription=None, output_transcription=NS(text=said) if said else None,
                                        model_turn=NS(parts=[NS(inline_data=NS(data=audio))]) if audio else None,
                                        interrupted=False, turn_complete=False), usage_metadata=None, tool_call=None))
    if usage:
        out.append(NS(server_content=None, tool_call=None, usage_metadata=NS(
            prompt_tokens_details=AUDIO + TEXT, response_tokens_details=AUDIO, prompt_token_count=1200, response_token_count=1000)))
    if done:
        out.append(NS(server_content=NS(input_transcription=None, output_transcription=None, model_turn=None,
                                        interrupted=False, turn_complete=True), usage_metadata=None, tool_call=None))
    return out


class FakeGemini:
    def __init__(self, turns, refuse_google_search=False):
        self.turns, self.refuse = list(turns), refuse_google_search
        self.configs, self.audio, self.tool_responses = [], [], []

    def connect(self, model, config):
        self.configs.append((model, config))
        fake = self

        @asynccontextmanager
        async def session():
            if fake.refuse and any("google_search" in t for t in config["tools"]):
                raise RuntimeError("google_search isn't supported")
            yield fake
        return session()

    async def receive(self):
        if not self.turns:
            await asyncio.sleep(3600)  # nothing more to say: wait (the call ends from the browser)
        for message in self.turns.pop(0):
            yield message

    async def send_audio(self, session, data):
        self.audio.append(data)

    async def send_text(self, session, text):
        self.texts = getattr(self, "texts", []) + [text]

    async def send_tool_responses(self, session, responses):
        self.tool_responses.append(responses)


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    get_settings.cache_clear()
    yield
    monkeypatch.setattr(gemini_live, "GATEWAY", None)
    get_settings.cache_clear()


def call(monkeypatch, fake, *, until=2, model="gemini-3.8-live"):
    """Run a call: send some audio, collect what the browser gets until `until` finished turns, then hang up."""
    monkeypatch.setattr(gemini_live, "GATEWAY", fake)
    got = {"json": [], "audio": []}
    with TestClient(create_app()) as c:
        set_setting("voice_provider_model", model)
        with c.websocket_connect("/ws/call/gemini") as ws:
            first = ws.receive_json()
            got["json"].append(first)
            if first["type"] != "live":
                return got
            ws.send_bytes(b"\x01\x00" * 160)
            finished = 0
            while finished < until:
                frame = ws.receive()
                if frame.get("bytes"):
                    got["audio"].append(frame["bytes"])
                elif frame.get("text"):
                    message = __import__("json").loads(frame["text"])
                    got["json"].append(message)
                    finished += message["type"] == "turn_complete"
            ws.send_json({"type": "end"})
        got["convo"] = first.get("conversation_id")
    return got


def test_a_gemini_call_streams_audio_saves_the_chat_and_counts_the_cost(gemini, monkeypatch):
    fake = FakeGemini([
        turn(heard="Assalam o alaikum, my rate is $25 an hour", said="Walaikum salam! Shukriya, noted.", audio=b"PCM-24k"),
        turn(heard="kya haal hai", said="Main bilkul theek hoon.", audio=b"PCM-2"),
    ])
    got = call(monkeypatch, fake)
    assert got["json"][0]["type"] == "live" and got["json"][0]["model"] == "gemini-3.8-live"
    assert got["audio"] == [b"PCM-24k", b"PCM-2"]  # his voice, passed straight to the browser
    assert fake.audio == [b"\x01\x00" * 160]  # your voice, passed straight to Gemini
    finals = [(m["type"], m["text"]) for m in got["json"] if m.get("final")]
    assert ("you", "Assalam o alaikum, my rate is $25 an hour") in finals and ("junior", "Walaikum salam! Shukriya, noted.") in finals
    with session_scope() as s:
        messages = s.scalars(select(Message).where(Message.conversation_id == got["convo"]).order_by(Message.id)).all()
        assert [(m.role, m.content) for m in messages][:2] == [
            ("user", "Assalam o alaikum, my rate is $25 an hour"), ("assistant", "Walaikum salam! Shukriya, noted.")]
        usage = s.scalars(select(Usage).where(Usage.agent == "junior_muneer_live")).all()
        per_turn = (1000 * 3.00 + 200 * 0.75 + 1000 * 12.00) / 1_000_000
        assert len(usage) == 2 and usage[0].cost_usd == pytest.approx(per_turn) and usage[0].model == "gemini-3.8-live"
        assert s.scalars(select(Usage).where(Usage.agent == "live_call")).first() is not None  # the call's minutes


def test_the_session_has_junior_the_urdish_voice_and_his_tools(gemini, monkeypatch):
    fake = FakeGemini([turn(heard="hello", said="Hi!")])
    call(monkeypatch, fake, until=1)
    model, config = fake.configs[0]
    assert model == "gemini-3.8-live" and config["response_modalities"] == ["AUDIO"]
    assert URDISH_INSTRUCTION in config["system_instruction"] and "Junior Muneer" in config["system_instruction"]
    # Gemini 3 has no Google Search on a free key: he searches with Junior's own web_search (your Search setting).
    assert not any("google_search" in t for t in config["tools"])
    names = [d["name"] for d in config["tools"][0]["function_declarations"]]
    assert names == ["ai_news", "pakistan_news", "ask_junior", "save_memory", "forget_memory", "web_search"]
    assert config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Charon"
    assert config["input_audio_transcription"] == {} and config["output_audio_transcription"] == {}


def test_gemini_25_live_gets_googles_own_search(gemini, monkeypatch):
    fake = FakeGemini([turn(heard="hello", said="Hi!")])
    call(monkeypatch, fake, until=1, model="gemini-2.5-flash-native-audio-preview-12-2025")
    tools = fake.configs[0][1]["tools"]
    assert tools[0] == {"google_search": {}} and not any("url_context" in t for t in tools)  # not taken together


def test_without_google_search_it_uses_our_web_search(gemini, monkeypatch):
    fake = FakeGemini([turn(heard="hi", said="Hello")], refuse_google_search=True)
    call(monkeypatch, fake, until=1, model="gemini-2.5-flash-native-audio-preview-12-2025")
    names = [d["name"] for d in fake.configs[1][1]["tools"][0]["function_declarations"]]
    assert "web_search" in names and not any("google_search" in t for t in fake.configs[1][1]["tools"])


def test_tools_run_with_the_same_safety_rules(gemini, monkeypatch):
    remember = NS(server_content=None, usage_metadata=None, tool_call=NS(function_calls=[
        NS(id="fc-1", name="save_memory", args={"fact": "Muneer charges $25 an hour", "your_words": "my rate is $25 an hour"})]))
    fake = FakeGemini([turn(heard="my rate is $25 an hour", said="Got it."), [remember], turn(said="Saved.")])
    got = call(monkeypatch, fake)
    assert any(m["type"] == "checking" and m["label"] == "save_memory" for m in got["json"])
    [[response]] = fake.tool_responses
    assert response["id"] == "fc-1" and response["response"]["result"].startswith("Saved as memory")
    with session_scope() as s:
        assert s.scalars(select(Memory.content)).all() == ["Muneer charges $25 an hour"]


def test_tool_failure_does_not_end_the_call(gemini, monkeypatch):
    from junior.calls import CallManager
    async def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(CallManager, "run_tool", fail)
    request = NS(server_content=None, usage_metadata=None, tool_call=NS(function_calls=[
        NS(id="fc-1", name="ask_junior", args={"question": "Find a file"})]))
    fake = FakeGemini([[request], turn(said="The task failed, but we can keep talking.")])
    got = call(monkeypatch, fake, until=1)
    assert not any(event["type"] == "error" for event in got["json"])
    assert "task failed" in fake.tool_responses[0][0]["response"]["result"]


def test_interruptions_reach_the_browser(gemini, monkeypatch):
    cut = NS(server_content=NS(input_transcription=None, output_transcription=None, model_turn=None, interrupted=True,
                               turn_complete=False), usage_metadata=None, tool_call=None)
    fake = FakeGemini([[cut] + turn(heard="wait", said="Sure.")])
    got = call(monkeypatch, fake, until=1)
    assert {"type": "interrupted"} in got["json"]


def test_no_key_or_not_chosen_or_no_minutes_left(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        got = call(monkeypatch, None)  # GATEWAY None and no key
        assert got["json"][0] == {"type": "error", "message": "Gemini calls need GEMINI_API_KEY in backend/.env (then restart)."}
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        get_settings.cache_clear()
        got = call(monkeypatch, FakeGemini([]), model="openai-realtime")
        assert "isn't the voice engine" in got["json"][0]["message"]
        with TestClient(create_app()):
            set_setting("call_minutes_per_day", 0)
        got = call(monkeypatch, FakeGemini([]))
        assert "limit" in got["json"][0]["message"]
    finally:
        monkeypatch.setattr(gemini_live, "GATEWAY", None)
        get_settings.cache_clear()


def test_turn_cost_prices_audio_and_text_separately():
    usage = NS(prompt_tokens_details=AUDIO + TEXT, response_tokens_details=AUDIO + TEXT)
    prices = {"audio_input": 3.0, "text_input": 0.75, "audio_output": 12.0, "text_output": 4.5}
    assert turn_cost(usage, prices) == pytest.approx((3000 + 150 + 12000 + 900) / 1_000_000)


def test_the_settings_and_limits_say_which_engine(gemini):
    with TestClient(create_app()) as c:
        assert c.get("/api/settings").json()["voice_provider_model"] == "openai-realtime"
        assert c.get("/api/call/limits").json()["engine"] == "openai"
        assert c.patch("/api/settings", json={"voice_provider_model": "gemini-3.8-live"}).status_code == 200
        limits = c.get("/api/call/limits").json()
        assert limits["engine"] == "gemini" and limits["model"] == "gemini-3.8-live" and limits["gemini_ready"] is True
        assert c.patch("/api/settings", json={"voice_provider_model": "gemini-9"}).status_code == 422
    assert session_config("x", "Puck")["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Puck"


def test_gemini_voice_samples_are_made_once_kept_and_counted(gemini, monkeypatch):
    fake = FakeGemini([turn(said="Assalam-o-Alaikum!", audio=b"\x01\x00" * 2400)])
    monkeypatch.setattr(gemini_live, "GATEWAY", fake)
    with TestClient(create_app()) as c:
        r = c.get("/api/voice/gemini-preview/Kore.wav")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
        model, config = fake.configs[0]
        assert model == gemini_live.SAMPLE_MODEL
        assert config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Kore"
        assert "tools" not in config  # a sample only speaks: no tools, no search
        assert fake.texts == [gemini_live.SAMPLE_TEXT]
        assert c.get("/api/voice/gemini-preview/Kore.wav").content == r.content  # kept: Gemini isn't asked again
        assert len(fake.configs) == 1
        with session_scope() as s:
            used = s.scalars(select(Usage).where(Usage.model == gemini_live.SAMPLE_MODEL)).all()
            assert len(used) == 1 and used[0].cost_usd > 0
        assert c.get("/api/voice/gemini-preview/Nobody.wav").status_code == 404


def test_gemini_voice_sample_without_a_key_says_so(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/voice/gemini-preview/Puck.wav")
            assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_urdu_written_in_a_wrong_script_is_heard_again_in_urdu_script(gemini, monkeypatch):
    """Found live: Gemini Live wrote Urdu, Punjabi and Saraiki speech in Bengali, Hindi or Chinese script."""
    import junior.voice as voice

    asked = {}

    async def our_stt(factory, data, content_type, seconds=None):
        asked.update(bytes=len(data), type=content_type, wav=data[:4])
        return {"text": "میں ٹھیک ہاں، تساں کیویں او؟", "audio_id": "x", "languages": [], "seconds": 2.0, "cost_usd": 0.0}

    monkeypatch.setattr(voice, "transcribe_bytes", our_stt)
    bengali = "আসসালামু"  # what Gemini wrote for Urdu speech

    class HearsFirst(FakeGemini):
        """Like the real Gemini: your voice arrives before its transcript of it."""

        async def receive(self):
            while not self.audio:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
            async for message in super().receive():
                yield message

    got = call(monkeypatch, HearsFirst([turn(heard=bengali, said="Main theek hoon!", audio=b"PCM")]), until=1)
    shown = [m["text"] for m in got["json"] if m["type"] == "you"]
    assert all(bengali not in t for t in shown) and "…" in shown  # never shown in the wrong script
    assert shown[-1] == "میں ٹھیک ہاں، تساں کیویں او؟"
    assert asked["type"] == "audio/wav" and asked["wav"] == b"RIFF" and asked["bytes"] > 44  # your audio, as WAV
    with session_scope() as s:
        saved = s.scalars(select(Message.content).where(Message.role == "user")).all()
    assert saved == ["میں ٹھیک ہاں، تساں کیویں او؟"]


def test_right_script_is_kept_without_hearing_again(gemini, monkeypatch):
    import junior.voice as voice

    def never(*args, **kwargs):
        raise AssertionError("heard again for no reason")

    monkeypatch.setattr(voice, "transcribe_bytes", never)
    call(monkeypatch, FakeGemini([turn(heard="آپ کیسے ہیں؟ How are you?", said="Theek!", audio=b"PCM")]), until=1)
    with session_scope() as s:
        assert s.scalars(select(Message.content).where(Message.role == "user")).all() == ["آپ کیسے ہیں؟ How are you?"]
