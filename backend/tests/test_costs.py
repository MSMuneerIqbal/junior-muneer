"""Cost tracking and the daily safety cap."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, chunked_answer, function_call, usage
from junior.db import Usage, session_scope
from junior.db.models import utcnow
from junior.main import create_app
from junior.settings_store import set_setting


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


def add_spend(cost: float, days_ago: int = 0) -> None:
    with session_scope() as s:
        s.add(
            Usage(
                agent="junior_muneer",
                model="gpt-6.1-sol",
                cost_usd=cost,
                created_at=utcnow() - timedelta(days=days_ago),
            )
        )


def test_spend_today_updates_after_each_message(client, model):
    assert client.get("/api/usage/today").json()["spent_usd"] == 0
    model.enqueue(chunked_answer("hi", u=usage(1000, 100)))
    done = chat(client, "Hello")[-1]

    today = client.get("/api/usage/today").json()
    # gpt-6.1-sol: 1000 in at $2/M + 100 out at $10/M
    assert today["spent_usd"] == pytest.approx(0.003) == pytest.approx(done["cost_usd"])
    assert today["by_mode"] == {"text": pytest.approx(0.003)}
    assert today["by_agent"] == {"junior_muneer": pytest.approx(0.003)}
    assert today["cap_usd"] == 5.0 and not today["cap_reached"]


def test_cap_blocks_the_next_message(client, model):
    set_setting("daily_cap_usd", 0.01)
    add_spend(0.01)
    events = chat(client, "Hello")
    assert events[-1]["type"] == "error"
    assert "Daily safety cap reached" in events[-1]["message"]
    assert model.calls == ()  # the AI was never called
    assert client.get("/api/usage/today").json()["cap_reached"]


def test_raising_the_cap_lets_messages_through_again(client, model):
    set_setting("daily_cap_usd", 0.01)
    add_spend(0.01)
    assert chat(client, "Hello")[-1]["type"] == "error"
    set_setting("daily_cap_usd", 5.0)
    model.enqueue(chunked_answer("Back!"))
    assert chat(client, "Hello again")[-1]["type"] == "done"


def test_yesterdays_spend_does_not_count(client, model):
    set_setting("daily_cap_usd", 0.01)
    add_spend(1.0, days_ago=2)
    model.enqueue(chunked_answer("ok"))
    assert chat(client, "Hello")[-1]["type"] == "done"


def test_runaway_tool_loop_is_stopped_mid_answer_and_its_cost_saved(client, model):
    set_setting("daily_cap_usd", 0.01)
    # First model call costs $0.02 (10k input tokens), more than the whole cap.
    model.extend(
        [
            {
                "output": [function_call("spending", {"period": "today"}, call_id="c1")],
                "usage": usage(10_000, 0),
            },
            chunked_answer("never reached"),
        ]
    )
    events = chat(client, "Loop forever please")
    assert events[-1]["type"] == "error"
    assert "used up what was left" in events[-1]["message"]
    assert len(model.calls) == 1  # the second call never happened
    with session_scope() as s:  # the $0.02 is still on the books
        assert s.scalar(select(Usage.cost_usd)) == pytest.approx(0.02)


def test_daily_history(client):
    add_spend(0.5)
    add_spend(0.25, days_ago=1)
    days = client.get("/api/usage/daily?days=7").json()
    assert [d["spent_usd"] for d in days] == [0.5, 0.25]
