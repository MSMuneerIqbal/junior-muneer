import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer
from junior.main import create_app


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    with TestClient(create_app(model_provider=lambda: (lambda _name: model))) as c:
        yield c


def chat(client, text):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def test_defaults(client):
    assert client.get("/api/settings").json() == {
        "user_name": "Muneer",
        "language": "match",
        "timezone": "Asia/Karachi",
        "daily_cap_usd": 5.0,
        "task_budget_usd": 0.5,
        "task_timeout_seconds": 600,
        "task_max_retries": 1,
        "paused": False,
        "tts_voice": "marin",
        "voice_accent": "pakistani",
        "tts_speed": 1.0,
        "voice_autoplay": True,
        "call_minutes_per_day": 30,
        "call_quality": "natural",
        "turn_taking": "balanced",
        "mic_type": "headset",
        "main_model": "",
        "helper_model": "",
        "web_search_provider": "openai",
        "computer_enabled": True,
        "desktop_enabled": False,
        "desktop_apps": ["notepad.exe"],
        "voice_engine": "openai",
        "voice_hear_model": "",
        "voice_speak_model": "",
        "voice_provider_model": "openai-realtime",
        "gemini_voice": "Charon",
        "vision_provider": "openai",
        "api_posts_per_day": 5,
        "news_digest_enabled": True,
        "news_digest_time": "07:30",
        "briefing_enabled": True,
        "briefing_time": "08:00",
        "memory_tidy_enabled": True,
        "news_email_enabled": True,
        "email_watch_enabled": True,
        "email_notify_whatsapp": True,
        "whatsapp_session_hours": 12,
        "whatsapp_carry_summary": True,
        "drive_share_default": "private",
    }


def test_change_and_it_is_logged(client):
    new = client.patch(
        "/api/settings", json={"user_name": " Ali ", "timezone": "Europe/London"}
    ).json()
    assert new["user_name"] == "Ali" and new["timezone"] == "Europe/London"
    rows = client.get("/api/activity?kind=setting").json()
    assert {r["name"] for r in rows} == {"user_name", "timezone"}
    assert next(r for r in rows if r["name"] == "user_name")["detail"] == {
        "before": "Muneer",
        "after": "Ali",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"user_name": "   "},
        {"language": "french"},
        {"timezone": "Mars/Olympus"},
        {"daily_cap_usd": -1},
        {"daily_cap_usd": 5000},
        {"drive_share_default": "owner"},
    ],
)
def test_bad_values_are_refused(client, body):
    assert client.patch("/api/settings", json=body).status_code == 422
    assert client.get("/api/settings").json()["daily_cap_usd"] == 5.0


def test_language_change_takes_effect(client, model):
    client.patch("/api/settings", json={"language": "urdu", "user_name": "Ali"})
    model.enqueue(chunked_answer("ٹھیک ہے"))
    chat(client, "hello")
    prompt = model.last_call.system_instructions
    assert "always reply in Urdu" in prompt and "friend of Ali" in prompt


def test_cap_change_takes_effect(client, model):
    client.patch("/api/settings", json={"daily_cap_usd": 0})
    assert "Daily safety cap reached" in chat(client, "hello")[-1]["message"]
    client.patch("/api/settings", json={"daily_cap_usd": 2})
    model.enqueue(chunked_answer("hi"))
    assert chat(client, "hello")[-1]["type"] == "done"


def test_models_view(client):
    data = client.get("/api/models").json()
    agents = {a["agent"]: a for a in data["agents"]}
    assert agents["junior_muneer"]["model"] == data["tiers"]["strong"]
    assert agents["summarizer"]["model"] == data["tiers"]["small"]
    assert agents["junior_muneer"]["price_per_million"]["output"] > 0
