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


def test_the_session_has_junior_the_urdish_voice_google_search_and_his_tools(gemini, monkeypatch):
    set_voice = FakeGemini([turn(heard="hello", said="Hi!")])
    call(monkeypatch, set_voice, until=1)
    model, config = set_voice.configs[0]
    assert model == "gemini-3.8-live" and config["response_modalities"] == ["AUDIO"]
    assert URDISH_INSTRUCTION in config["system_instruction"] and "Junior Muneer" in config["system_instruction"]
    assert config["tools"][0] == {"google_search": {}} and config["tools"][1] == {"url_context": {}}
    names = [d["name"] for d in config["tools"][2]["function_declarations"]]
    assert names == ["ai_news", "pakistan_news", "ask_junior", "save_memory", "forget_memory"]
    assert config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Charon"
    assert config["input_audio_transcription"] == {} and config["output_audio_transcription"] == {}


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
