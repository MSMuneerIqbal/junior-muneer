import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call, usage, with_web_search
from junior.audit import MAX_TEXT, audit
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
        while ws.receive_json()["type"] not in ("done", "error"):
            pass


def activity(client, **params):
    return client.get("/api/activity", params=params).json()


def test_one_message_gives_readable_log_lines(client, model):
    model.extend(
        [
            [function_call("spending", {"period": "today"}, call_id="c1")],
            chunked_answer("You spent $0.", u=usage(1000, 100)),
        ]
    )
    chat(client, "What did I spend?")

    rows = activity(client)
    assert [(r["kind"], r["name"], r["result"]) for r in rows] == [
        ("agent_run", "junior_muneer", "ok"),  # newest first
        ("tool_call", "spending", "ok"),
    ]
    run, tool = rows
    assert run["detail"]["model_calls"] == 2
    assert run["detail"]["steps"] == ["Checking your spending"]
    assert run["cost_usd"] > 0 and run["conversation_id"] is not None
    assert tool["detail"]["arguments"] == '{"period":"today"}'
    assert "Spend (today)" in tool["detail"]["result"]


def test_web_search_and_refused_memory_are_logged(client, model):
    save = function_call(
        "save_memory", {"fact": "Rate $5", "your_words": "rate is $5 now"}, call_id="m1"
    )
    model.extend([with_web_search("rates", [save]), chunked_answer("ok")])
    chat(client, "Search rates")

    rows = activity(client)
    names = [(r["kind"], r["name"], r["result"]) for r in rows]
    assert ("web_search", "web_search", "ok") in names
    assert ("tool_call", "save_memory", "refused") in names
    search = next(r for r in rows if r["kind"] == "web_search")
    assert search["detail"]["query"] == "rates" and search["cost_usd"] > 0


def test_blocked_runs_are_logged(client):
    set_setting("daily_cap_usd", 0.0)
    chat(client, "Hello")
    run = activity(client, kind="agent_run")[0]
    assert run["result"] == "blocked"
    assert "Daily safety cap" in run["detail"]["error"]


def test_memory_page_changes_are_logged(client):
    m = client.post("/api/memories", json={"content": "Likes tea"}).json()
    client.patch(f"/api/memories/{m['id']}", json={"content": "Likes green tea"})
    client.delete(f"/api/memories/{m['id']}")
    rows = activity(client, kind="memory")
    assert [r["name"] for r in rows] == ["deleted", "edited", "added on Memory page"]
    assert rows[1]["detail"] == {"id": m["id"], "before": "Likes tea", "after": "Likes green tea"}


def test_filter_and_paging(client):
    for i in range(5):
        audit("system", f"event {i}")
    audit("setting", "paused")
    assert [r["name"] for r in activity(client, kind="setting")] == ["paused"]
    first = activity(client, kind="system", limit=2)
    assert [r["name"] for r in first] == ["event 4", "event 3"]
    more = activity(client, kind="system", limit=2, before_id=first[-1]["id"])
    assert [r["name"] for r in more] == ["event 2", "event 1"]
    assert len(activity(client, kind="system,setting")) == 6


def test_long_text_is_cut(client):
    audit("system", "big", detail={"text": "x" * 5000})
    text = activity(client)[0]["detail"]["text"]
    assert len(text) < MAX_TEXT + 40 and text.endswith("chars)")
