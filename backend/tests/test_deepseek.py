"""Choosing text models in Settings, including DeepSeek."""

import pytest
from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, usage
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
