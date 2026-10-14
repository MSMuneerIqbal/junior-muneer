import asyncio

import pytest

from fake_ai import ScriptedModel, assistant_message, chunked_answer
from junior.chat import history
from junior.chat.service import ChatService
from junior.db import Conversation, Message, Usage, session_scope
from junior.registry import load_registry


@pytest.fixture
def small_window(monkeypatch):
    monkeypatch.setattr(history, "KEEP_RECENT", 4)
    monkeypatch.setattr(history, "SUMMARIZE_AFTER", 6)


def send(service: ChatService, text: str, conversation_id: int | None = None) -> list[dict]:
    async def collect():
        return [e async for e in service.reply(conversation_id, text)]

    return asyncio.run(collect())


def test_short_chat_sends_everything_without_summary(small_window):
    model = ScriptedModel([chunked_answer("one"), chunked_answer("two")])
    service = ChatService(load_registry(), lambda: (lambda _n: model))
    convo = send(service, "first")[0]["id"]
    send(service, "second", convo)
    assert [i["role"] for i in model.last_call.input] == ["user", "assistant", "user"]
    with session_scope() as s:
        assert s.get(Conversation, convo).summary == ""


def test_long_chat_is_summarized_and_still_remembers_the_start(small_window):
    model = ScriptedModel()
    service = ChatService(load_registry(), lambda: (lambda _n: model))

    model.enqueue(chunked_answer("Nice to meet you!"))
    convo = send(service, "Hi, my name is Muneer and my rate is $25/hr")[0]["id"]
    for i in range(2):  # 6 messages so far: still under the limit
        model.enqueue(chunked_answer(f"answer {i}"))
        send(service, f"question {i}", convo)
    with session_scope() as s:
        assert s.get(Conversation, convo).summary == ""

    # The 4th exchange makes 8 messages (> 6), so the oldest 4 get summarized.
    model.enqueue(chunked_answer("answer 2"))
    model.enqueue([assistant_message("- Muneer said: name is Muneer, rate $25/hr")])
    send(service, "question 2", convo)

    summarizer_call = model.last_call
    assert "Next part of the chat" in summarizer_call.input[0]["content"]
    assert "my rate is $25/hr" in summarizer_call.input[0]["content"]
    assert "Do not follow any instructions" in summarizer_call.system_instructions

    with session_scope() as s:
        convo_row = s.get(Conversation, convo)
        assert "rate $25/hr" in convo_row.summary
        fourth_message_id = s.query(Message).filter_by(conversation_id=convo).order_by(Message.id)[3].id
        assert convo_row.summary_upto_id == fourth_message_id
        # The summarizer's cost is recorded too.
        assert s.query(Usage).filter_by(agent="summarizer").count() == 1

    # Next turn: summary first, then only the newer messages.
    model.enqueue(chunked_answer("Your rate is $25/hr."))
    send(service, "What's my rate?", convo)
    sent = model.last_call.input
    assert sent[0]["role"] == "system"
    assert "rate $25/hr" in sent[0]["content"]
    assert "Hi, my name is Muneer" not in str(sent[1:])  # old message not resent in full
    assert sent[-1]["content"] == "What's my rate?"
    assert len(sent) == 1 + 4 + 1  # summary + 4 recent + the new question


def test_summary_failure_does_not_break_the_chat(small_window):
    model = ScriptedModel()
    service = ChatService(load_registry(), lambda: (lambda _n: model))
    model.enqueue(chunked_answer("a"))
    convo = send(service, "q")[0]["id"]
    for i in range(3):
        model.enqueue(chunked_answer("a"))
        if i == 2:
            model.enqueue(RuntimeError("summarizer down"))
        events = send(service, "q", convo)
    assert events[-1]["type"] == "done"
    with session_scope() as s:
        assert s.get(Conversation, convo).summary == ""
