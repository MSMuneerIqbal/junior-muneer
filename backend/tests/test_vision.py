"""Reading photos with your choice of AI: OpenAI's small vision model or DeepSeek V4.1 Flash (falls back to OpenAI)."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from junior import ai_client, reading
from junior.agent.context import TurnContext
from junior.config import get_settings
from junior.main import create_app
from junior.settings_store import all_settings, set_setting


class FakeClient:
    """Stands in for both providers' clients; remembers each request."""

    def __init__(self, calls, base_url, fail):
        self.calls, self.base_url, self.fail = calls, base_url, fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.responses = SimpleNamespace(create=self._responses)

    async def _chat(self, **request):
        self.calls.append(("deepseek", self.base_url, request))
        if self.fail:
            raise RuntimeError("DeepSeek is busy")
        usage = SimpleNamespace(prompt_tokens=1100, completion_tokens=120, prompt_tokens_details=None)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="DeepSeek: an invoice, total Rs 5,000."))])

    async def _responses(self, **request):
        self.calls.append(("openai", self.base_url, request))
        usage = SimpleNamespace(input_tokens=1200, output_tokens=100, input_tokens_details=None)
        return SimpleNamespace(usage=usage, output_text="OpenAI: an invoice, total Rs 5,000.")


@pytest.fixture
def vision(monkeypatch):
    monkeypatch.setenv("FAKE_AI", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    get_settings.cache_clear()
    calls, state = [], {"fail": False}
    monkeypatch.setattr(ai_client, "ai_client", lambda key, base_url=None: FakeClient(calls, base_url, state["fail"]))
    with TestClient(create_app()):
        yield (lambda: TurnContext(conversation_id=None, settings=all_settings())), calls, state
    get_settings.cache_clear()


def look(context):
    return asyncio.run(reading.look_at_image(b"\xff\xd8\xff jpeg", "image/jpeg", "what's the total?", context))


def test_openai_reads_photos_by_default(vision):
    context, calls, _ = vision
    ctx = context()
    assert look(ctx) == "OpenAI: an invoice, total Rs 5,000."
    assert [c[0] for c in calls] == ["openai"]


def test_deepseek_v41_flash_reads_them_when_chosen(vision):
    context, calls, _ = vision
    set_setting("vision_provider", "deepseek")
    ctx = context()
    assert look(ctx) == "DeepSeek: an invoice, total Rs 5,000."
    [(who, base_url, request)] = calls
    assert who == "deepseek" and base_url == "https://api.deepseek.com" and request["model"] == "deepseek-flash"
    text, image = request["messages"][0]["content"]
    assert text["type"] == "text" and "what's the total?" in text["text"]
    assert image["type"] == "image_url" and image["image_url"]["url"].startswith("data:image/jpeg;base64,")
    [usage] = ctx.usage
    assert usage.model == "deepseek:deepseek-flash" and usage.agent == "image_reader"
    assert usage.cost_usd == pytest.approx((1100 * 0.30 + 120 * 1.20) / 1_000_000)


def test_if_deepseek_fails_openai_reads_it(vision):
    context, calls, state = vision
    set_setting("vision_provider", "deepseek")
    state["fail"] = True
    assert look(context()) == "OpenAI: an invoice, total Rs 5,000."
    assert [c[0] for c in calls] == ["deepseek", "openai"]


def test_the_setting_and_the_model_name(vision):
    with TestClient(create_app()) as c:
        assert c.get("/api/settings").json()["vision_provider"] == "openai"
        assert c.patch("/api/settings", json={"vision_provider": "deepseek"}).status_code == 200
        flash = next(m for m in c.get("/api/models/choices").json()["choices"] if m["model"] == "deepseek:deepseek-flash")
    assert flash["label"] == "DeepSeek V4.1 Flash" and "sees images" in flash["note"]
