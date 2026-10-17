"""P7-02: long requests finish in the background and post their result to the same chat."""

import time

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message, chunked_answer, function_call
from junior.agent.builder import NoApiKeyError
from junior.agent.context import TurnContext
from junior.agent.tools import run_in_background_for
from junior.background import MAX_RUNNING, new_task, recover_interrupted
from junior.main import create_app

ASK = "Write me 3 LinkedIn posts for next week about my MCP server"
START = function_call("run_in_background", {"title": "3 LinkedIn posts", "request": ASK}, call_id="bg1")


def chat(c, text):
    with c.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        events = []
        while not events or events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())
    return events


def wait_for(c, conversation_id, status, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        tasks = c.get(f"/api/tasks?conversation_id={conversation_id}").json()
        if tasks and tasks[0]["status"] == status:
            return tasks[0]
        time.sleep(0.1)
    raise AssertionError(f"task didn't reach {status}: {tasks}")


def test_a_long_request_finishes_in_the_background():
    model = ScriptedModel(
        [
            [START],
            chunked_answer("I'm on it: 3 LinkedIn posts. Keep chatting; they'll appear here."),
            [assistant_message("Here are your 3 posts: one, two, three.")],  # the background turn
        ]
    )
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        events = chat(c, ASK)
        done = events[-1]
        assert done["type"] == "done" and "I'm on it" in done["text"]
        assert any(s["label"] == "Starting it in the background" for s in done["steps"])
        convo = done["conversation_id"]

        task = wait_for(c, convo, "done")
        assert task["title"] == "3 LinkedIn posts" and task["message_id"] is not None

        texts = [(m["role"], m["content"]) for m in c.get(f"/api/conversations/{convo}/messages").json()]
        assert texts[0] == ("user", ASK)
        assert texts[1][1].startswith("I'm on it")  # your answer first...
        assert texts[2] == ("assistant", "**Done in the background: 3 LinkedIn posts**\n\nHere are your 3 posts: one, two, three.")

        # The background turn saw the chat and the task, and can't start another one.
        last = model.calls[-1]
        assert "[Background task 1] Do this now, fully: " + ASK in last.input[-1]["content"]


def test_background_work_cant_start_more_background_work():
    context = TurnContext(conversation_id=1, settings={})
    context.background = True
    assert run_in_background_for(context, "x", "y").startswith("NOT started: you're already working in the background")
    context = TurnContext(conversation_id=1, settings={})  # a live call: no background tasks
    assert run_in_background_for(context, "x", "y").startswith("NOT started: background tasks work in the text chat")


def test_paused_or_too_many_means_do_it_now():
    model = ScriptedModel([[START], chunked_answer("Paused, so here it is now.")])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        c.post("/api/pause", json={"paused": True})
        chat(c, ASK)
        said = [o["output"] for call in model.calls for o in call.input if isinstance(o, dict) and o.get("type") == "function_call_output"]
        assert said[-1].startswith("NOT started: everything is paused")
        assert c.get("/api/tasks").json() == []

        c.post("/api/pause", json={"paused": False})
        for n in range(MAX_RUNNING):
            new_task(None, f"t{n}", "x")
        model.extend([[START], chunked_answer("Busy, doing it now.")])
        chat(c, ASK)
        said = [o["output"] for call in model.calls for o in call.input if isinstance(o, dict) and o.get("type") == "function_call_output"]
        assert said[-1].startswith(f"NOT started: {MAX_RUNNING} tasks are already running")


def test_a_failed_background_task_says_so_in_the_chat():
    model = ScriptedModel([[START], chunked_answer("I'm on it.")])
    calls = {"n": 0}

    def provider():
        calls["n"] += 1
        if calls["n"] > 1:  # the background turn
            raise NoApiKeyError("No OpenAI API key yet.")
        return lambda _n: model

    with TestClient(create_app(model_provider=provider)) as c:
        convo = chat(c, ASK)[-1]["conversation_id"]
        task = wait_for(c, convo, "failed")
        assert task["error"] == "No OpenAI API key yet."
        last = c.get(f"/api/conversations/{convo}/messages").json()[-1]
        assert last["content"] == "**I couldn't finish “3 LinkedIn posts” in the background.** No OpenAI API key yet."


def test_tasks_stopped_by_a_restart_are_marked_failed():
    with TestClient(create_app(model_provider=lambda: (lambda _n: None))) as c:
        new_task(None, "half done", "x")
        assert recover_interrupted() == 1
        task = c.get("/api/tasks").json()[0]
        assert task["status"] == "failed" and "restarted" in task["error"]
