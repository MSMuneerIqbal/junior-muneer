import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, chunked_answer, function_call, usage
from junior.agent.builder import NoApiKeyError
from junior.db import Message, Usage, session_scope
from junior.main import create_app


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    with TestClient(create_app(model_provider=lambda: (lambda _name: model))) as c:
        yield c


def chat(client, text, conversation_id=None):
    """Send one message over the WebSocket; return all events up to done/error."""
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": conversation_id, "text": text})
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in ("done", "error"):
                return events


def test_answer_streams_in_pieces_and_is_saved(client, model):
    model.enqueue(chunked_answer("Hi Muneer, good to see you!", u=usage(1000, 100)))
    events = chat(client, "Hello there")

    kinds = [e["type"] for e in events]
    assert kinds[0] == "conversation" and kinds[1] == "user_message"
    assert kinds.count("delta") > 3
    done = events[-1]
    assert done["type"] == "done"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == done["text"]
    assert done["cost_usd"] > 0

    convo_id = events[0]["id"]
    messages = client.get(f"/api/conversations/{convo_id}/messages").json()
    assert [(m["role"], m["source"]) for m in messages] == [
        ("user", "user"),
        ("assistant", "assistant"),
    ]
    assert messages[1]["content"] == "Hi Muneer, good to see you!"
    assert messages[1]["cost_usd"] == pytest.approx(done["cost_usd"])
    with session_scope() as s:
        row = s.scalars(select(Usage)).one()
        assert (row.input_tokens, row.output_tokens, row.mode) == (1000, 100, "text")
        assert row.message_id == messages[1]["id"]


def test_second_message_sees_the_earlier_chat(client, model):
    model.enqueue(chunked_answer("Nice to meet you, Muneer."))
    convo_id = chat(client, "My name is Muneer")[0]["id"]
    model.enqueue(chunked_answer("Your name is Muneer."))
    events = chat(client, "What's my name?", convo_id)

    assert events[-1]["type"] == "done"
    sent = model.last_call.input
    assert [i["role"] for i in sent] == ["user", "assistant", "user"]
    assert sent[0]["content"] == "My name is Muneer"


def test_steps_are_saved_for_show_work(client, model):
    model.extend(
        [[function_call("spending", {"period": "today"}, call_id="c1")], chunked_answer("$0.")]
    )
    events = chat(client, "What did I spend today?")
    steps = [e for e in events if e["type"] == "step"]
    assert [s["status"] for s in steps] == ["running", "done"]
    convo_id = events[0]["id"]
    saved = client.get(f"/api/conversations/{convo_id}/messages").json()[1]["steps"]
    assert saved[0]["name"] == "spending" and saved[0]["status"] == "done"


def test_missing_api_key_is_shown_in_the_chat():
    def no_key():
        raise NoApiKeyError("No OpenAI API key yet.")

    with TestClient(create_app(model_provider=no_key)) as client:
        events = chat(client, "Hello")
    assert events[-1] == {"type": "error", "message": "No OpenAI API key yet."}
    with session_scope() as s:  # your message is still saved
        assert s.scalars(select(Message.content)).all() == ["Hello"]


def test_unknown_chat_and_empty_message_give_errors(client):
    assert chat(client, "hi", 999)[-1]["type"] == "error"
    assert chat(client, "   ")[-1] == {"type": "error", "message": "Empty message."}


def test_list_rename_pin_search_delete(client, model):
    model.extend([chunked_answer("ok"), chunked_answer("ok")])
    first = chat(client, "Plan my LinkedIn week")[0]["id"]
    second = chat(client, "Fiverr order question")[0]["id"]

    listed = client.get("/api/conversations").json()
    assert [c["id"] for c in listed] == [second, first]  # newest first
    assert listed[0]["title"] == "Fiverr order question"
    assert listed[0]["message_count"] == 2

    assert client.patch(f"/api/conversations/{first}", json={"title": "LinkedIn"}).status_code == 200
    client.patch(f"/api/conversations/{first}", json={"pinned": True})
    listed = client.get("/api/conversations").json()
    assert [(c["id"], c["title"], c["pinned"]) for c in listed][0] == (first, "LinkedIn", True)

    # Search finds titles and message text.
    assert [c["id"] for c in client.get("/api/conversations?q=fiverr").json()] == [second]
    assert [c["id"] for c in client.get("/api/conversations?q=week").json()] == [first]

    assert client.delete(f"/api/conversations/{second}").status_code == 204
    assert client.get(f"/api/conversations/{second}/messages").status_code == 404
    with session_scope() as s:
        assert all(m.conversation_id == first for m in s.scalars(select(Message)))


def test_create_empty_chat_and_404s(client):
    created = client.post("/api/conversations", json={}).json()
    assert created["title"] == "New chat" and created["message_count"] == 0
    assert client.patch("/api/conversations/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/conversations/999").status_code == 404
    assert client.patch(f"/api/conversations/{created['id']}", json={"title": ""}).status_code == 422
