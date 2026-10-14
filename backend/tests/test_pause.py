import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer
from junior.chat import history
from junior.db import Conversation, session_scope
from junior.main import create_app
from junior.pause import PausedError, ensure_not_paused


@pytest.fixture
def model():
    return ScriptedModel()


def make_client(model):
    return TestClient(create_app(model_provider=lambda: (lambda _name: model)))


def chat(client, text, conversation_id=None):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": conversation_id, "text": text})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def test_pause_switch_and_it_survives_a_restart(model):
    with make_client(model) as client:
        assert client.get("/api/pause").json() == {"paused": False}
        assert client.post("/api/pause", json={"paused": True}).json() == {"paused": True}
    with make_client(model) as client:  # a fresh app = a restart
        assert client.get("/api/pause").json() == {"paused": True}
        client.post("/api/pause", json={"paused": False})
        assert client.get("/api/pause").json() == {"paused": False}
        names = [r["name"] for r in client.get("/api/activity?kind=setting").json()]
        assert names == ["resumed", "paused"]


def test_chat_still_works_and_he_knows_he_is_paused(model):
    with make_client(model) as client:
        client.post("/api/pause", json={"paused": True})
        model.enqueue(chunked_answer("I'm paused, but happy to chat!"))
        assert chat(client, "Hi")[-1]["type"] == "done"
        assert "PAUSE IS ON" in model.last_call.system_instructions

        client.post("/api/pause", json={"paused": False})
        model.enqueue(chunked_answer("All running."))
        chat(client, "Hi again")
        assert "PAUSE IS ON" not in model.last_call.system_instructions


def test_no_background_summary_while_paused(model, monkeypatch):
    monkeypatch.setattr(history, "KEEP_RECENT", 2)
    monkeypatch.setattr(history, "SUMMARIZE_AFTER", 3)
    with make_client(model) as client:
        client.post("/api/pause", json={"paused": True})
        model.enqueue(chunked_answer("a"))
        convo = chat(client, "one")[0]["id"]
        model.enqueue(chunked_answer("b"))  # 4 messages now: would summarize if running
        chat(client, "two", convo)
        model.assert_complete()  # no summarizer call was made
        with session_scope() as s:
            assert s.get(Conversation, convo).summary == ""


def test_actions_refuse_while_paused(model):
    with make_client(model) as client:
        ensure_not_paused("Test action")  # fine while running
        client.post("/api/pause", json={"paused": True})
        with pytest.raises(PausedError, match="Test action skipped"):
            ensure_not_paused("Test action")
