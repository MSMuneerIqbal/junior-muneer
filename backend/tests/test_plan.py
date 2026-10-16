"""P7-01: a request with several parts gets a live checklist, ticked off as each part finishes, saved with the answer."""

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call
from junior.main import create_app


def items(*statuses):
    parts = ["Spending this week", "Your recent chats"]
    return {"items": [{"text": p, "status": s} for p, s in zip(parts, statuses)]}


def test_a_checklist_for_several_parts():
    model = ScriptedModel(
        [
            [function_call("update_plan", items("pending", "pending"), call_id="p1")],
            # Independent parts in one go.
            [
                function_call("spending", {"period": "week"}, call_id="t1"),
                function_call("recent_chats", {"days": 7}, call_id="t2"),
            ],
            [function_call("update_plan", items("done", "done"), call_id="p2")],
            chunked_answer("You spent $0 this week, and you have no recent chats."),
        ]
    )
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "How much did I spend this week, and what did we chat about?"})
            events = []
            while not events or events[-1]["type"] not in ("done", "error"):
                events.append(ws.receive_json())

        live = [e for e in events if e["type"] == "step" and e["id"] == "plan"]
        assert [e["label"] for e in live] == ["Plan: 0 of 2 done", "Plan: 2 of 2 done"]  # updated live
        assert live[-1]["status"] == "done" and [i["status"] for i in live[-1]["items"]] == ["done", "done"]

        done = events[-1]
        names = [s.get("name") for s in done["steps"]]
        assert "update_plan" not in names and "spending" in names and "recent_chats" in names  # the checklist isn't a step line
        plan = next(s for s in done["steps"] if s["id"] == "plan")
        assert plan["kind"] == "plan" and plan["label"] == "Plan: 2 of 2 done"

        saved = c.get(f"/api/conversations/{done['conversation_id']}/messages").json()[-1]
        assert any(s["id"] == "plan" and s["items"][0]["text"] == "Spending this week" for s in saved["steps"])  # kept with the answer


def test_an_empty_checklist_is_refused():
    from junior.agent.context import TurnContext
    from junior.agent.tools import PlanItem, update_plan_for

    context = TurnContext(conversation_id=None, settings={})
    assert update_plan_for(context, [PlanItem(text="  ")]).startswith("NOT")
    assert context.pending_events == []
