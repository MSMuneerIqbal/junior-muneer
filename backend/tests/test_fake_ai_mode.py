"""The fake-AI mode used to try the dashboard (and by the frontend tests)."""

import pytest
from fastapi.testclient import TestClient

from junior.agent import fake
from junior.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FAKE_AI", "true")
    monkeypatch.setattr(fake, "DELAY_SECONDS", 0)
    monkeypatch.setattr(fake, "CHUNK", 6)
    from junior.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def chat(client, text):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def test_echoes_in_pieces(client):
    events = chat(client, "Hello there")
    assert sum(e["type"] == "delta" for e in events) > 3
    assert "You said" in events[-1]["text"] and "Hello there" in events[-1]["text"]


def test_search_shows_a_step(client):
    events = chat(client, "search the news")
    steps = [e for e in events if e["type"] == "step"]
    assert [s["status"] for s in steps] == ["running", "done"]


def test_remember_saves_through_the_real_tool(client):
    events = chat(client, "remember I like green tea")
    assert any(e["type"] == "memory" for e in events)
    assert [m["content"] for m in client.get("/api/memories").json()] == ["I like green tea"]
