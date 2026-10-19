"""Gemini as the third chat provider (Google's OpenAI-compatible endpoint), Gemini web search (Google Search + URL
reading), and OpenAI stepping in when Gemini is rate-limited or busy."""

import asyncio
from types import SimpleNamespace as NS

import httpx
import openai
import pytest
from agents import OpenAIChatCompletionsModel
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, usage
from junior import websearch
from junior.agent.builder import NoApiKeyError, openai_model_provider
from junior.agent.context import TurnContext
from junior.config import get_settings
from junior.main import create_app
from junior.settings_store import all_settings, set_setting

GEMINI_MODELS = ["gemini:gemini-3.8-flash", "gemini:gemini-3.1-flash-lite", "gemini:gemini-4-argon"]


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
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


def test_gemini_goes_through_googles_openai_compatible_endpoint(keys):
    model = openai_model_provider()("gemini:gemini-3.8-flash")
    assert isinstance(model, OpenAIChatCompletionsModel) and model.model == "gemini-3.8-flash"
    assert str(model._client.base_url) == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert model._client.api_key == "gemini-test-key"


def test_gemini_streaming_asks_for_token_counts_so_its_cost_is_counted(keys):
    """Gemini streams without token counts unless asked; then every reply cost $0."""
    import json

    from agents import ModelSettings, ModelTracing
    from openai import AsyncOpenAI

    sent = {}
    sse = (
        'data: {"id":"1","object":"chat.completion.chunk","created":1,"model":"gemini-3.1-flash-lite",'
        '"choices":[{"index":0,"delta":{"role":"assistant","content":"hi"},"finish_reason":"stop"}]}\n\n'
        'data: {"id":"1","object":"chat.completion.chunk","created":1,"model":"gemini-3.1-flash-lite","choices":[],'
        '"usage":{"prompt_tokens":120,"completion_tokens":7,"total_tokens":127}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    model = openai_model_provider()("gemini:gemini-3.1-flash-lite")
    model._client = AsyncOpenAI(api_key="k", base_url="https://example.test/v1/",
                                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def run():
        events = []
        async for event in model.stream_response(None, "hi", ModelSettings(), [], None, [], ModelTracing.DISABLED):
            events.append(event)
        return events

    events = asyncio.run(run())
    assert sent["stream_options"] == {"include_usage": True}
    done = [e for e in events if getattr(e, "type", "") == "response.completed"][-1]
    assert done.response.usage.input_tokens == 120 and done.response.usage.output_tokens == 7


def test_without_a_gemini_key_it_says_which_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(NoApiKeyError, match="GEMINI_API_KEY"):
            openai_model_provider()("gemini:gemini-3.8-flash")
    finally:
        get_settings.cache_clear()


def test_the_three_gemini_models_are_in_settings_with_short_notes(keys):
    with TestClient(create_app(model_provider=lambda: (lambda n: ScriptedModel()))) as client:
        choices = {c["model"]: c for c in client.get("/api/models/choices").json()["choices"]}
    for name in GEMINI_MODELS:
        assert choices[name]["provider"] == "Gemini" and choices[name]["ready"] is True and choices[name]["note"]
    assert choices["gemini:gemini-3.8-flash"]["label"] == "Gemini 3.8 Flash"
    assert choices["gemini:gemini-4-argon"]["label"] == "Gemini 4 Argon"
    assert choices["gemini:gemini-3.8-flash"]["price_per_million"] == {"input": 0.75, "output": 3.75}


def test_choosing_gemini_is_used_and_costed():
    names = []
    model = ScriptedModel([chunked_answer("Salam from Gemini!", u=usage(1_000_000, 0))])
    with TestClient(create_app(model_provider=lambda: (lambda n: names.append(n) or model))) as client:
        assert client.patch("/api/settings", json={"main_model": "gemini:gemini-3.8-flash"}).status_code == 200
        done = chat(client, "hi")[-1]
    assert names == ["gemini:gemini-3.8-flash"] and done["text"] == "Salam from Gemini!"
    assert done["cost_usd"] == pytest.approx(0.75)  # 1M input tokens at the paid price (the cap is never under-counted)


class RateLimited(ScriptedModel):
    """Like a free-tier Gemini at its limit: refuses at once."""

    async def stream_response(self, *args, **kwargs):
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        raise openai.RateLimitError("Resource has been exhausted", response=httpx.Response(429, request=request), body=None)
        yield None  # never reached


def test_a_rate_limited_gemini_hands_the_answer_to_openai():
    used = []
    openai_model = ScriptedModel([chunked_answer("Hi from OpenAI!")])

    def provider(name):
        used.append(name)
        return RateLimited() if name.startswith("gemini:") else openai_model

    with TestClient(create_app(model_provider=lambda: provider)) as client:
        client.patch("/api/settings", json={"main_model": "gemini:gemini-3.1-flash-lite"})
        events = chat(client, "hi")
    assert events[-1]["type"] == "done" and events[-1]["text"] == "Hi from OpenAI!"
    assert used == ["gemini:gemini-3.1-flash-lite", "gpt-6.1-sol"]
    note = next(e for e in events if e["type"] == "step" and e.get("name") == "fallback")
    assert note["label"] == "Gemini hit its rate limit, so gpt-6.1-sol answered"


def test_openai_rate_limits_are_not_hidden():
    with TestClient(create_app(model_provider=lambda: (lambda n: RateLimited()))) as client:
        events = chat(client, "hi")  # OpenAI itself (the default) refuses: say so, don't loop
    assert events[-1]["type"] == "error"


# ---- Gemini web search ---------------------------------------------------------------------


class FakeGeminiClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.aio = NS(models=NS(generate_content=self._generate))

    async def _generate(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.fail:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        chunks = [NS(web=NS(uri="https://www.dawn.com/news/1", title="Dawn")), NS(web=NS(uri="https://www.dawn.com/news/1", title="Dawn"))]
        return NS(text="- Petrol is Rs 260 a litre (16 Oct).", usage_metadata=NS(prompt_token_count=1000, candidates_token_count=200),
                  candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks))])


class Helpers:
    def __init__(self):
        self.asked = []

    async def run(self, agent, prompt, context):
        self.asked.append(agent)
        return "OpenAI researcher: findings."


def search(query):
    ctx = TurnContext(conversation_id=None, settings=all_settings())
    ctx.helpers = Helpers()
    return asyncio.run(websearch.search_for(ctx, query)), ctx


def test_gemini_search_uses_google_search_and_url_reading_with_sources(keys, monkeypatch):
    fake = FakeGeminiClient()
    monkeypatch.setattr(websearch, "GEMINI_CLIENT", fake)
    with TestClient(create_app()):
        set_setting("web_search_provider", "gemini")
        text, ctx = search("petrol price in Pakistan today")
    [call] = fake.calls
    # Gemini 2.5 Flash: free Google Search on a free key (Gemini 3 has none), plus reading links.
    assert call["model"] == "gemini-2.5-flash" and call["config"] == {"tools": [{"google_search": {}}, {"url_context": {}}]}
    assert "petrol price in Pakistan today" in call["contents"]
    assert "Petrol is Rs 260 a litre" in text and "Sources:\n- Dawn: https://www.dawn.com/news/1" in text
    assert text.count("https://www.dawn.com/news/1") == 1  # the same source once
    assert "START OF THEIR TEXT (Google search results via Gemini" in text and ctx.outside_content_seen
    [u] = ctx.usage
    assert u.model == "gemini:gemini-2.5-flash" and u.cost_usd == pytest.approx((1000 * 0.30 + 200 * 2.50) / 1_000_000)
    assert ctx.helpers.asked == []


def test_if_gemini_search_fails_openai_searches(keys, monkeypatch):
    monkeypatch.setattr(websearch, "GEMINI_CLIENT", FakeGeminiClient(fail=True))
    with TestClient(create_app()):
        set_setting("web_search_provider", "gemini")
        text, ctx = search("anything")
    assert text == "OpenAI researcher: findings." and ctx.helpers.asked == ["web_researcher"]
    assert any("Gemini search didn't work" in e.get("label", "") for e in ctx.pending_events)


def test_spend_shows_gemini(keys, monkeypatch):
    from junior.agent.context import ModelUsage
    from junior.chat.history import save_usage
    from junior.db import session_scope

    with TestClient(create_app()) as c:
        with session_scope() as s:
            save_usage(s, [ModelUsage("junior_muneer", "gemini:gemini-3.8-flash", 0, 0, 0, 0, 0.002),
                           ModelUsage("web_search", "gemini:gemini-3.8-flash", 0, 0, 0, 1, 0.001),
                           ModelUsage("junior_muneer_live", "gemini-3.8-live", 0, 0, 0, 0, 0.004)], None, None)
        today = c.get("/api/usage/today").json()
    assert today["by_provider"]["gemini"] == pytest.approx(0.007)
    assert today["web_search"]["gemini"] == pytest.approx(0.001)
