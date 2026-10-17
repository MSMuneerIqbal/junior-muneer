"""P7-03: "What happened today?" from the app's records, and the morning briefing (facts only)."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message, chunked_answer, function_call
from junior.db import ApprovalItem, BackgroundTask, Conversation, Idea, Job, Memory, Message, Order, Usage, session_scope
from junior.main import create_app
from junior.registry import load_registry
from junior.reports import briefing_due, briefing_prompt, briefing_today, day_facts, make_briefing, morning_briefing
from junior.settings_store import all_settings, set_setting

TZ = "Asia/Karachi"  # UTC+5
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)  # 14:00 in Lahore


def seed(base: datetime = NOW):
    """Today's things two hours before `base`, and one message a day earlier."""
    TODAY, YESTERDAY, NOW_ = base - timedelta(hours=2), base - timedelta(days=1), base  # noqa: N806
    with session_scope() as s:
        chat = Conversation(title="Weekly plan", kind="text")
        s.add(chat)
        s.flush()
        s.add_all(
            [
                Message(conversation_id=chat.id, role="user", source="user", content="hi", created_at=TODAY),
                Message(conversation_id=chat.id, role="user", source="user", content="voice", audio_file="a1", created_at=TODAY),
                Message(conversation_id=chat.id, role="user", source="user", content="old", created_at=YESTERDAY),
                ApprovalItem(kind="copy", platform="linkedin", item_type="post", title="MCP launch", text="t", original_text="t", status="posted",
                             created_at=TODAY, posted_at=TODAY),
                ApprovalItem(kind="copy", platform="upwork", item_type="proposal", title="Clinic bot", text="t", original_text="t", status="waiting", created_at=TODAY),
                Job(title="RAG chatbot", score=7, verdict="apply", created_at=TODAY, updated_at=TODAY),
                Order(title="Logo for Sam", status="active", due_at=NOW_ + timedelta(hours=5), created_at=TODAY, updated_at=TODAY),
                Idea(platform="linkedin", title="Fractional Marla", created_at=TODAY),
                Memory(content="My sister's wedding is in December", created_at=TODAY, updated_at=TODAY),
                BackgroundTask(title="3 LinkedIn posts", request="x", status="done", created_at=TODAY),
                Usage(agent="junior_muneer", model="m", mode="text", cost_usd=0.12, created_at=TODAY),
                Usage(agent="junior_muneer", model="m", mode="voice", cost_usd=0.05, created_at=TODAY),
            ]
        )


def app():
    return TestClient(create_app(model_provider=lambda: (lambda _n: None)))


def test_what_happened_today_is_full_and_correct():
    with app():
        seed()
        facts = day_facts("today", TZ, NOW)
    assert facts.startswith("# What happened: today (Sat 17 Oct, 00:00 to Sat 17 Oct, 14:00, your time zone)")
    for line in [
        "- 1 chat, 2 messages from you (1 by voice).",  # yesterday's message isn't counted
        "Topics: “Weekly plan”.",
        "- 2 drafts made: LinkedIn post (1), Upwork proposal (1).",
        "- Marked as posted or sent: “LinkedIn post: MCP launch”.",
        "- Waiting for your OK right now: 1.",
        "- Jobs scored: “RAG chatbot” 7/10 apply.",
        "- Orders saved: “Logo for Sam”.",
        "- Open order “Logo for Sam”: due Sat 17 Oct, 19:00.",
        "- Post ideas saved: 1 (LinkedIn).",
        "- Remembered: “My sister's wedding is in December”.",
        "- Done: “3 LinkedIn posts”.",
        "- $0.17 on AI (text $0.12, voice $0.05).",
    ]:
        assert line in facts, line


def test_yesterday_and_an_empty_day():
    with app():
        seed()
        assert "- 1 chat, 1 message from you." in day_facts("yesterday", TZ, NOW)
        empty = day_facts("yesterday", TZ, NOW - timedelta(days=30))
        assert empty.endswith("Nothing recorded: no chats, drafts, jobs, orders or memories.")


def test_junior_answers_what_happened_from_the_records():
    model = ScriptedModel(
        [
            [function_call("what_happened", {"period": "today"}, call_id="r1")],
            chunked_answer("Busy day! One post went out and a proposal is waiting for you."),
        ]
    )
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        seed(datetime.now(UTC) + timedelta(hours=1, minutes=59))  # things from a minute ago
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "What happened today?"})
            while (e := ws.receive_json())["type"] not in ("done", "error"):
                pass
        said = next(o["output"] for o in model.calls[-1].input if isinstance(o, dict) and o.get("type") == "function_call_output")
        assert "Jobs scored: “RAG chatbot” 7/10 apply." in said and said.endswith("Summarize only them; don't add anything.)")
        assert any(s["label"] == "Checking what happened" for s in e["steps"])
        assert c.get("/api/report?period=week").json()["facts"].startswith("# What happened: week")
        assert c.get("/api/report?period=year").status_code == 422


def test_the_morning_briefing_once_a_day_from_facts_only():
    model = ScriptedModel([[assistant_message("Good morning, Muneer! One proposal is waiting for you.")]])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        seed()
        settings = all_settings()
        prompt = briefing_prompt(settings, NOW)
        assert "### Yesterday" in prompt and "### Today so far and what's next" in prompt and "Logo for Sam" in prompt

        set_setting("briefing_time", "08:00")
        early = datetime.now(UTC).replace(hour=0, minute=30)  # 05:30 in Lahore
        assert not briefing_due(all_settings(), early)

        convo = asyncio.run(make_briefing(load_registry(), lambda: (lambda _n: model)))
        assert briefing_today(TZ) == convo
        with session_scope() as s:
            chat = s.get(Conversation, convo)
            assert chat.kind == "briefing" and chat.title.startswith("☀ Morning briefing · ")
            text = chat.messages[0].content
        assert text == "Good morning, Muneer! One proposal is waiting for you."
        assert "### Yesterday" in model.calls[0].input[-1]["content"]  # the writer got the facts
        assert c.get("/api/briefing/today").json() == {"conversation_id": convo}

        # Once a day: asking again gives the same chat, with no new AI call.
        assert c.post("/api/briefing/now").json() == {"conversation_id": convo}
        assert len(model.calls) == 1
        assert not briefing_due(all_settings())


def test_no_briefing_while_paused_or_switched_off():
    model = ScriptedModel([])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        c.post("/api/pause", json={"paused": True})
        set_setting("briefing_time", "00:00")
        asyncio.run(morning_briefing(load_registry(), lambda: (lambda _n: model)))
        assert briefing_today(TZ) is None and not model.calls

        c.post("/api/pause", json={"paused": False})
        assert c.patch("/api/settings", json={"briefing_enabled": False}).status_code == 200
        assert not briefing_due(all_settings())
        assert c.patch("/api/settings", json={"briefing_time": "25:00"}).status_code == 422
