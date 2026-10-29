"""Choosing text models in Settings, including DeepSeek."""

import pytest
from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call, usage
from junior.agent.builder import NoApiKeyError, openai_model_provider
from junior.config import get_settings
from junior.main import create_app
from junior.settings_store import set_setting


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def chat(client, text):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def test_provider_gives_deepseek_through_its_own_api(keys):
    provide = openai_model_provider()
    ds = provide("deepseek:deepseek-flash")
    assert isinstance(ds, OpenAIChatCompletionsModel)
    assert ds.model == "deepseek-flash"
    assert str(ds._client.base_url).startswith("https://api.deepseek.com")
    assert isinstance(provide("gpt-6.1-sol"), OpenAIResponsesModel)


def test_deepseek_without_a_key_gives_a_clear_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    get_settings.cache_clear()
    with pytest.raises(NoApiKeyError, match="DEEPSEEK_API_KEY"):
        openai_model_provider()("deepseek:deepseek-flash")


def test_choosing_deepseek_in_settings_is_used_and_costed():
    names = []
    model = ScriptedModel([chunked_answer("Salam!", u=usage(1_000_000, 0))])

    def provider(name):
        names.append(name)
        return model

    with TestClient(create_app(model_provider=lambda: provider)) as client:
        r = client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        assert r.status_code == 200
        done = chat(client, "hi")[-1]
        assert names == ["deepseek:deepseek-flash"]
        assert done["cost_usd"] == pytest.approx(0.30)  # 1M input tokens at DeepSeek's peak price
        table = {a["agent"]: a["model"] for a in client.get("/api/models").json()["agents"]}
        assert table["junior_muneer"] == "deepseek:deepseek-flash"
        assert table["web_researcher"] == "gpt-6-luna"  # web search stays on OpenAI


def test_back_to_the_default_with_an_empty_choice():
    names = []
    model = ScriptedModel([chunked_answer("hi")])
    with TestClient(create_app(model_provider=lambda: (lambda n: names.append(n) or model))) as c:
        set_setting("main_model", "")
        chat(c, "hi")
    assert names == ["gpt-6.1-sol"]


def test_unknown_models_are_refused():
    with TestClient(create_app(model_provider=lambda: (lambda n: ScriptedModel()))) as client:
        assert client.patch("/api/settings", json={"main_model": "gpt-99"}).status_code == 422


def test_choices_say_which_are_ready(keys):
    with TestClient(create_app(model_provider=lambda: (lambda n: ScriptedModel()))) as client:
        data = client.get("/api/models/choices").json()
    by_model = {c["model"]: c for c in data["choices"]}
    assert by_model["deepseek:deepseek-flash"]["ready"] is True
    assert by_model["deepseek:deepseek-flash"]["provider"] == "DeepSeek"
    assert by_model["gpt-6.1-sol"]["ready"] is True
    assert data["defaults"]["main_model"] == "gpt-6.1-sol"


def test_choices_without_a_deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app(model_provider=lambda: (lambda n: ScriptedModel()))) as client:
        data = client.get("/api/models/choices").json()
    flash = next(c for c in data["choices"] if c["model"] == "deepseek:deepseek-flash")
    assert flash["ready"] is False and flash["key_env"] == "DEEPSEEK_API_KEY"


class StalledModel(ScriptedModel):
    """Like a busy DeepSeek: accepts the request, then sends nothing."""

    def __init__(self, words_first: bool = False):
        super().__init__()
        self.words_first = words_first

    async def stream_response(self, *args, **kwargs):
        import asyncio

        if self.words_first:  # send the start of an answer, then go silent
            for event in chunked_answer("Let me think").stream_events:
                yield event
                if getattr(event, "type", "") == "response.output_text.delta":
                    break
        await asyncio.sleep(3600)
        yield None  # never reached


def test_busy_deepseek_falls_back_to_openai(monkeypatch):
    import junior.chat.service as service

    monkeypatch.setattr(service, "FIRST_WORDS_SECONDS", 0.3)
    openai_model = ScriptedModel([chunked_answer("Hi from OpenAI!")])
    used = []

    def provider(name):
        used.append(name)
        return StalledModel() if name.startswith("deepseek:") else openai_model

    with TestClient(create_app(model_provider=lambda: provider)) as client:
        client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        events = chat(client, "hi")
        done = events[-1]
        assert done["type"] == "done" and done["text"] == "Hi from OpenAI!"
        assert used == ["deepseek:deepseek-flash", "gpt-6.1-sol"]
        note = next(e for e in events if e["type"] == "step" and e.get("name") == "fallback")
        assert note["label"] == "DeepSeek is busy right now, so gpt-6.1-sol answered"
        saved = client.get(f"/api/conversations/{done['conversation_id']}/messages").json()[1]
        assert saved["steps"][0]["name"] == "fallback"  # shows in Show work


def test_deepseek_stalling_mid_answer_gives_a_clear_error(monkeypatch):
    import junior.chat.service as service

    monkeypatch.setattr(service, "STALL_SECONDS", 0.3)
    with TestClient(
        create_app(model_provider=lambda: (lambda name: StalledModel(words_first=True)))
    ) as client:
        client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        events = chat(client, "hi")
    assert events[-1]["type"] == "error"
    assert "stopped responding mid-answer" in events[-1]["message"]


def test_openai_is_never_cut_off_by_the_deadline(monkeypatch):
    import junior.chat.service as service

    monkeypatch.setattr(service, "FIRST_WORDS_SECONDS", 0.0001)
    model = ScriptedModel([chunked_answer("fine")])
    with TestClient(create_app(model_provider=lambda: (lambda n: model))) as client:
        assert chat(client, "hi")[-1]["type"] == "done"


def test_voice_messages_use_openai_even_when_deepseek_is_chosen():
    from junior.voice import FakeVoice

    used = []
    model = ScriptedModel([chunked_answer("Voice reply"), chunked_answer("Typed reply")])
    app = create_app(model_provider=lambda: (lambda n: used.append(n) or model), voice=FakeVoice)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        audio_id = client.post(
            "/api/voice/transcribe",
            files={"audio": ("v.webm", b"\x1aE\xdf\xa3" + b"\0" * 500, "audio/webm")},
            data={"seconds": "3"},
        ).json()["audio_id"]
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "hello", "audio_id": audio_id})
            while ws.receive_json()["type"] not in ("done", "error"):
                pass
        chat(client, "typed hello")
    assert used == ["gpt-6.1-sol", "deepseek:deepseek-flash"]  # voice: OpenAI; typed: DeepSeek


def test_lookups_in_calls_use_openai_even_when_deepseek_is_chosen():
    import asyncio as aio

    from junior.calls import CallManager
    from junior.registry import load_registry
    from test_calls import FakeGateway, heard, tool

    set_setting("main_model", "deepseek:deepseek-flash")
    used = []
    model = ScriptedModel([chunked_answer("Your spend is low.")])
    FakeGateway.events = [heard("What did I spend?"), tool("ask_junior", '{"question": "Spend today?"}')]
    manager = CallManager(FakeGateway, load_registry(), lambda: (lambda n: used.append(n) or model))

    async def go():
        call, _ = await manager.start("v=0")
        await call.task

    aio.run(go())
    assert used == ["gpt-6.1-sol"]


def test_a_turn_that_never_ends_is_stopped_at_the_overall_limit(monkeypatch):
    """Even OpenAI (no first-words limit) can't hang a chat forever: the whole answer has a time limit."""
    import junior.chat.service as service

    monkeypatch.setattr(service, "TURN_SECONDS", 1)
    with TestClient(create_app(model_provider=lambda: (lambda name: StalledModel()))) as client:
        events = chat(client, "hi")
    assert events[-1]["type"] == "error"
    assert "took over" in events[-1]["message"] and "background task" in events[-1]["message"]


class SlowToolWriter(ScriptedModel):
    """Like DeepSeek in the live failure: quick steps first, then a long time writing a whole Google Doc into a tool
    call, with no visible text."""

    calls = 0

    async def stream_response(self, *args, **kwargs):
        import asyncio

        from openai.types.responses import ResponseFunctionCallArgumentsDeltaEvent

        SlowToolWriter.calls += 1
        if SlowToolWriter.calls == 2:  # after the first tool step: the slow part
            for n in range(20):  # 2 s of writing, longer than the 1 s silence limit below
                await asyncio.sleep(0.1)
                yield ResponseFunctionCallArgumentsDeltaEvent(
                    type="response.function_call_arguments.delta", delta='"more doc text", ', item_id="fc1",
                    output_index=0, sequence_number=n)
        async for event in super().stream_response(*args, **kwargs):
            yield event


def test_a_long_tool_call_isnt_mistaken_for_silence(monkeypatch):
    import junior.agent.runner as runner
    import junior.chat.service as service

    monkeypatch.setattr(service, "STALL_SECONDS", 1.0)
    monkeypatch.setattr(runner, "ALIVE_SECONDS", 0.05)
    SlowToolWriter.calls = 0
    model = SlowToolWriter([[function_call("spending", {"period": "today"}, call_id="s1")], chunked_answer("Your doc is ready.")])
    with TestClient(create_app(model_provider=lambda: (lambda name: model))) as client:
        client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        events = chat(client, "make me a long doc")
    assert events[-1]["type"] == "done" and events[-1]["text"] == "Your doc is ready."
    assert not any(e["type"] == "alive" for e in events)  # only for the silence check, never sent to the chat


def test_a_slow_tool_isnt_mistaken_for_silence(monkeypatch):
    """Found live: an 18-second web search plus DeepSeek's quiet thinking counted as 60 s of silence."""
    import time as _time

    import junior.agent.tools as tools
    import junior.chat.service as service

    monkeypatch.setattr(service, "STALL_SECONDS", 0.3)

    real = tools.spending.on_invoke_tool

    async def slow(ctx, args):
        await __import__("asyncio").sleep(1.0)  # the tool works for longer than the silence limit
        return await real(ctx, args)

    monkeypatch.setattr(tools.spending, "on_invoke_tool", slow)
    model = ScriptedModel([[function_call("spending", {"period": "today"}, call_id="s1")], chunked_answer("You spent a little.")])
    started = _time.monotonic()
    with TestClient(create_app(model_provider=lambda: (lambda name: model))) as client:
        client.patch("/api/settings", json={"main_model": "deepseek:deepseek-flash"})
        events = chat(client, "how much did I spend?")
    assert events[-1]["type"] == "done" and events[-1]["text"] == "You spent a little."
    assert _time.monotonic() - started >= 1.0
