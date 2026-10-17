"""P7-04: smarter memory - dates in the prompt, recall beyond the newest 100, and a safe weekly tidy-up."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message, chunked_answer, function_call
from junior.agent.context import TurnContext
from junior.agent.tools import save_memory_for
from junior.db import Conversation, Memory, Message, session_scope
from junior.main import create_app
from junior.memories import memories_for_prompt, search_memories
from junior.memory_tidy import ArchivePick, check_picks, tidy_due, tidy_memories, weekly_tidy
from junior.registry import load_registry
from junior.settings_store import all_settings, set_setting
from junior.timeutil import zone

NOW = datetime.now(UTC)


def app(model=None):
    return TestClient(create_app(model_provider=lambda: (lambda _n: model)))


def add(content, days_ago=0, archived=False):
    with session_scope() as s:
        m = Memory(content=content, created_at=NOW - timedelta(days=days_ago), updated_at=NOW)
        if archived:
            m.archived_at, m.archive_reason = NOW, "Same as another one"
        s.add(m)
        s.flush()
        return m.id


def test_memories_show_their_date_and_archived_ones_are_hidden():
    with app():
        add("My exam is next week", days_ago=40)
        add("Old rate $20/hr", archived=True)
        text = memories_for_prompt("", "Asia/Karachi")
    saved = (NOW - timedelta(days=40)).astimezone(zone("Asia/Karachi")).strftime("%d %b %Y")
    assert f"(saved {saved}) My exam is next week" in text
    assert "Old rate" not in text


def test_with_many_memories_the_ones_that_fit_your_message_come_too():
    with app():
        wedding = add("My sister's wedding is on 12 December in Multan", days_ago=200)
        for n in range(120):
            add(f"Small fact number {n}", days_ago=100 - n % 50)
        text = memories_for_prompt("When is my sister's wedding?", "UTC")
        assert f"[{wedding}]" in text  # an old memory, but it fits the message
        assert "(Showing 100 of 121 memories" in text and "recall_memory" in text
        assert text.count("\n- [") + 1 == 100
        found = search_memories("wedding Multan", "UTC")
        assert "sister's wedding is on 12 December" in found
        assert search_memories("cricket", "UTC") == "No saved memory matches that."


def test_junior_can_recall_older_memories():
    model = ScriptedModel([[function_call("recall_memory", {"query": "hourly rate"}, call_id="r1")], chunked_answer("Your rate is $25/hr.")])
    with app(model) as c:
        add("Muneer's hourly rate is $25")
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "What's my rate again?"})
            while (e := ws.receive_json())["type"] not in ("done", "error"):
                pass
        said = next(o["output"] for o in model.calls[-1].input if isinstance(o, dict) and o.get("type") == "function_call_output")
        assert "Muneer's hourly rate is $25" in said
        assert any(s["label"] == "Looking through your memories" for s in e["steps"])


def test_only_safe_suggestions_are_archived():
    with app():
        keep = add("Rate $25/hr", days_ago=3)
        dup = add("My rate is $25 per hour", days_ago=30)
        fresh = add("I'm learning Rust", days_ago=2)
        old = add("My exam is next week", days_ago=40)
        others = [add(f"Fact {n}", days_ago=20) for n in range(6)]
        with session_scope() as s:
            active = {m.id: m for m in s.query(Memory).all()}
            s.expunge_all()
    picks = [
        ArchivePick(id=dup, kind="duplicate", keep_id=keep, reason="Same as your rate memory"),
        ArchivePick(id=999, kind="duplicate", keep_id=keep, reason="Not a real memory"),
        ArchivePick(id=fresh, kind="outdated", reason="Too new to call outdated"),
        ArchivePick(id=old, kind="outdated", reason="The exam was weeks ago"),
        ArchivePick(id=others[0], kind="duplicate", reason="No memory to keep"),
        ArchivePick(id=keep, kind="duplicate", keep_id=dup, reason="The kept one is being archived"),
        ArchivePick(id=others[1], kind="outdated", reason="  "),
    ]
    accepted = check_picks(picks, active, NOW)
    assert [p.id for p in accepted] == [dup, old]

    # At most 30% in one run.
    many = [ArchivePick(id=i, kind="outdated", reason="Old") for i in [old, *others]]
    assert len(check_picks(many, active, NOW)) == 3  # 30% of 10


def test_the_tidy_up_archives_and_you_can_restore():
    with app() as c:
        keep = add("Rate $25/hr", days_ago=3)
        dup = add("My rate is $25 per hour", days_ago=30)
        reply = {"archive": [{"id": dup, "kind": "duplicate", "keep_id": keep, "reason": f"Same as {keep}: your rate is $25/hr"}]}
        model = ScriptedModel([[assistant_message(json.dumps(reply))]])
        result = asyncio.run(tidy_memories(load_registry(), lambda: (lambda _n: model), force=True))
        assert result["archived"] == [{"id": dup, "content": "My rate is $25 per hour", "reason": f"Same as {keep}: your rate is $25/hr"}]
        assert "[" + str(keep) + "]" in model.calls[0].input[-1]["content"]  # the tidier saw the memories with numbers

        assert [m["id"] for m in c.get("/api/memories").json()] == [keep]
        archived = c.get("/api/memories/archived").json()
        assert archived[0]["id"] == dup and archived[0]["reason"].startswith("Same as")
        assert c.post(f"/api/memories/{dup}/restore").status_code == 200
        assert {m["id"] for m in c.get("/api/memories").json()} == {keep, dup}
        assert c.post(f"/api/memories/{dup}/restore").status_code == 404
        assert all_settings()["memory_tidied_at"]
        assert "memory_tidied_at" not in c.get("/api/settings").json()


def test_saying_an_archived_memory_again_brings_it_back():
    with app():
        gone = add("Muneer prefers short proposals", archived=True)
        with session_scope() as s:
            chat = Conversation(title="Proposals")
            s.add(chat)
            s.flush()
            msg = Message(conversation_id=chat.id, role="user", source="user", content="I prefer short proposals")
            s.add(msg)
            s.flush()
            msg_id = msg.id
        context = TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=[msg_id])
        said = save_memory_for(context, "Muneer prefers short proposals", "I prefer short proposals")
        assert said == f"Remembered again: memory {gone} was archived by a tidy-up, and it's back."
        assert "short proposals" in memories_for_prompt()


def test_the_weekly_tidy_up_waits_its_turn():
    model = ScriptedModel([])
    with app(model) as c:
        assert tidy_due(all_settings())  # never run yet
        set_setting("memory_tidied_at", (NOW - timedelta(days=2)).isoformat())
        assert not tidy_due(all_settings())
        set_setting("memory_tidied_at", (NOW - timedelta(days=8)).isoformat())
        assert tidy_due(all_settings())

        asyncio.run(weekly_tidy(load_registry(), lambda: (lambda _n: model)))  # under 10 memories: no AI call
        assert not model.calls and not tidy_due(all_settings())

        set_setting("memory_tidied_at", "")
        c.post("/api/pause", json={"paused": True})
        for n in range(12):
            add(f"Fact {n}")
        asyncio.run(weekly_tidy(load_registry(), lambda: (lambda _n: model)))  # paused: nothing runs
        assert not model.calls
        assert c.patch("/api/settings", json={"memory_tidy_enabled": False}).status_code == 200
        assert not tidy_due(all_settings())


def test_exact_duplicates_dont_count_against_the_limit():
    """Same words (checked by code) are always safe to archive; only AI judgement calls are capped."""
    with app():
        ids = [add("Same fact") for _ in range(4)] + [add(f"Other {n}", days_ago=20) for n in range(4)]
        with session_scope() as s:
            active = {m.id: m for m in s.query(Memory).all()}
            s.expunge_all()
    picks = [ArchivePick(id=i, kind="duplicate", keep_id=ids[0], reason="Same words") for i in ids[1:4]]
    picks += [ArchivePick(id=i, kind="outdated", reason="Old") for i in ids[4:]]
    accepted = check_picks(picks, active, NOW)
    assert [p.id for p in accepted if p.kind == "duplicate"] == ids[1:4]  # every exact duplicate
    assert len([p for p in accepted if p.kind == "outdated"]) == 2  # judgement calls: 30% of 8
