"""Live calls: the backend side (session set-up, transcripts, tools, cost, limits)."""

import asyncio
import contextlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, chunked_answer
from junior.calls import CallManager, call_cost
from junior.db import Conversation, Memory, Message, Usage, session_scope
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_store import set_setting


class FakeConnection:
    def __init__(self, events):
        self.events = list(events)
        self.sent: list[dict] = []

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self.events:
            await asyncio.sleep(0)
            yield event

    async def send(self, event):
        self.sent.append(event)


class FakeGateway:
    last: "FakeGateway | None" = None
    events: list = []

    def __init__(self):
        FakeGateway.last = self
        self.sessions: list[dict] = []
        self.hung_up: list[str] = []
        self.conn = FakeConnection(FakeGateway.events)

    async def create_call(self, sdp, session):
        self.sessions.append(session)
        return "v=0 fake-answer", "rtc_test123"

    @contextlib.asynccontextmanager
    async def connect(self, call_id):
        yield self.conn

    async def hangup(self, call_id):
        self.hung_up.append(call_id)


def usage_event(audio_in=1000, text_in=500, audio_out=2000, text_out=100):
    return {
        "type": "response.done",
        "response": {
            "usage": {
                "input_tokens": audio_in + text_in,
                "output_tokens": audio_out + text_out,
                "input_token_details": {
                    "text_tokens": text_in,
                    "audio_tokens": audio_in,
                    "cached_tokens": 0,
                    "cached_tokens_details": {"text_tokens": 0, "audio_tokens": 0},
                },
                "output_token_details": {"text_tokens": text_out, "audio_tokens": audio_out},
            }
        },
    }


def heard(text):
    return {"type": "conversation.item.input_audio_transcription.completed", "transcript": text}


def said(text):
    return {"type": "response.output_audio_transcript.done", "transcript": text}


def tool(name, arguments, call_id="fc1"):
    return {
        "type": "response.function_call_arguments.done",
        "name": name,
        "arguments": arguments,
        "call_id": call_id,
    }


def run_call(events, model=None):
    """Start a call with these events from OpenAI and wait until it ends."""
    FakeGateway.events = events
    model = model or ScriptedModel()
    manager = CallManager(FakeGateway, load_registry(), lambda: (lambda _n: model))

    async def go():
        call, answer = await manager.start("v=0 offer")
        await call.task
        return call, answer

    call, answer = asyncio.run(go())
    return call, answer, FakeGateway.last


def test_session_has_his_personality_voice_tools_and_urdu_transcription():
    set_setting("tts_voice", "cedar")
    call, answer, gw = run_call([])
    session = gw.sessions[0]
    assert answer == "v=0 fake-answer"
    assert session["model"] == "gpt-realtime-2.1-mini"
    assert "You are **Junior Muneer**" in session["instructions"]
    assert "You are on a live voice call" in session["instructions"]
    assert "{{" not in session["instructions"]
    assert session["audio"]["output"]["voice"] == "cedar"
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-transcribe"
    assert "Urdu script" in session["audio"]["input"]["transcription"]["prompt"]
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    assert {t["name"] for t in session["tools"]} == {"ask_junior", "save_memory", "forget_memory"}


def test_both_sides_are_saved_as_a_call_chat_with_cost_and_minutes():
    call, _, _ = run_call(
        [heard("Hi Junior, how are you?"), said("I'm great, Muneer!"), usage_event()]
    )
    with session_scope() as s:
        convo = s.get(Conversation, call.conversation_id)
        assert convo.kind == "call" and convo.title.startswith("Live call")
        assert [(m.role, m.source, m.content) for m in convo.messages] == [
            ("user", "user", "Hi Junior, how are you?"),
            ("assistant", "assistant", "I'm great, Muneer!"),
        ]
        rows = s.scalars(select(Usage).where(Usage.mode == "call")).all()
        cost_row = next(r for r in rows if r.agent == "junior_muneer_live")
        minutes_row = next(r for r in rows if r.agent == "live_call")
    # gpt-realtime-2.1-mini: audio in $10, text in $0.60, audio out $20, text out $2.40 per 1M
    assert cost_row.cost_usd == pytest.approx((1000 * 10 + 500 * 0.6 + 2000 * 20 + 100 * 2.4) / 1e6)
    assert "seconds" in minutes_row.extra


def test_memory_from_your_spoken_words_is_saved():
    call, _, gw = run_call(
        [
            heard("By the way, my hourly rate is 25 dollars."),
            tool("save_memory", '{"fact": "Rate is $25/hr", "your_words": "my hourly rate is 25 dollars"}'),
        ]
    )
    with session_scope() as s:
        assert s.scalars(select(Memory.content)).all() == ["Rate is $25/hr"]
    output = gw.conn.sent[0]
    assert output["type"] == "conversation.item.create"
    assert output["item"]["call_id"] == "fc1" and output["item"]["output"].startswith("Saved")
    assert gw.conn.sent[1] == {"type": "response.create"}


def test_ask_junior_answers_and_then_blocks_memory_for_that_turn():
    model = ScriptedModel([chunked_answer("It's sunny in Lahore, 31 degrees.")])
    call, _, gw = run_call(
        [
            heard("What's the weather in Lahore? Also my rate is 40 dollars."),
            tool("ask_junior", '{"question": "Weather in Lahore today?"}', "a1"),
            tool("save_memory", '{"fact": "Rate $40", "your_words": "my rate is 40 dollars"}', "m1"),
            heard("Okay, my rate is 40 dollars."),  # a new turn of yours
            tool("save_memory", '{"fact": "Rate $40", "your_words": "my rate is 40 dollars"}', "m2"),
        ],
        model,
    )
    outputs = [e["item"]["output"] for e in gw.conn.sent if e["type"] == "conversation.item.create"]
    assert outputs[0] == "It's sunny in Lahore, 31 degrees."
    assert outputs[1].startswith("NOT saved: this turn includes outside text")
    assert outputs[2].startswith("Saved")
    with session_scope() as s:
        assert s.scalars(select(Memory.content)).all() == ["Rate $40"]
        # The full Junior Muneer's cost is part of the call's cost.
        assert s.scalars(select(Usage).where(Usage.agent == "junior_muneer")).one().mode == "call"


def test_cap_reached_during_a_call_hangs_up():
    set_setting("daily_cap_usd", 0.05)
    call, _, gw = run_call([heard("hello"), usage_event(audio_out=5000)])  # ~$0.11
    assert gw.hung_up == ["rtc_test123"]
    assert call.end_reason == "daily cost cap reached"


def test_an_empty_call_leaves_no_chat():
    call, _, _ = run_call([])
    with session_scope() as s:
        assert s.get(Conversation, call.conversation_id) is None
        assert s.scalars(select(Message)).all() == []


def test_call_cost_counts_cached_tokens_at_the_cached_price():
    prices = {"audio_input": 10, "audio_cached_input": 0.3, "text_input": 0.6, "text_cached_input": 0.06}
    usage = {
        "input_token_details": {
            "text_tokens": 1000,
            "audio_tokens": 1000,
            "cached_tokens_details": {"text_tokens": 400, "audio_tokens": 500},
        },
        "output_token_details": {},
    }
    assert call_cost(usage, prices) == pytest.approx(
        (600 * 0.6 + 400 * 0.06 + 500 * 10 + 500 * 0.3) / 1e6
    )


# ---- the HTTP side ----------------------------------------------------------------


@pytest.fixture
def client():
    FakeGateway.events = []
    app = create_app(model_provider=lambda: (lambda _n: ScriptedModel()), realtime=FakeGateway)
    with TestClient(app) as c:
        yield c


def test_start_returns_the_answer_and_ids(client):
    r = client.post("/api/call/start", json={"sdp": "v=0 offer from browser"})
    assert r.status_code == 200
    body = r.json()
    assert body["sdp"] == "v=0 fake-answer" and body["call_id"] == "rtc_test123"
    assert isinstance(body["conversation_id"], int)


def test_daily_call_minutes_limit(client):
    set_setting("call_minutes_per_day", 0)
    r = client.post("/api/call/start", json={"sdp": "v=0 offer from browser"})
    assert r.status_code == 429 and "live-call limit" in r.json()["detail"]
    limits = client.get("/api/call/limits").json()
    assert limits["minutes_allowed"] == 0 and limits["model"] == "gpt-realtime-2.1-mini"


def test_cap_blocks_starting_a_call(client):
    set_setting("daily_cap_usd", 0)
    assert client.post("/api/call/start", json={"sdp": "v=0 offer from browser"}).status_code == 429


def test_end_unknown_call(client):
    assert client.post("/api/call/end", json={"call_id": "nope"}).json() == {"ended": False}


def test_an_empty_call_is_still_logged_and_counted():
    from junior.db import AuditLog

    run_call([])
    with session_scope() as s:
        ended = s.scalars(select(AuditLog).where(AuditLog.name == "live_call")).all()[-1]
        assert ended.detail["event"] == "ended" and ended.conversation_id is None
        assert s.scalars(select(Usage).where(Usage.agent == "live_call")).one().extra["seconds"] >= 0


def test_show_work_on_spoken_answers_and_call_summary():
    model = ScriptedModel([chunked_answer("Sunny, 31 degrees.")])
    call, _, _ = run_call(
        [
            heard("What's the weather?"),
            tool("ask_junior", '{"question": "Weather in Lahore?"}', "a1"),
            usage_event(),  # the response that called the tool (no words)
            said("It's sunny, 31 degrees."),
            usage_event(),  # the response that spoke
        ],
        model,
    )
    with session_scope() as s:
        answer = s.scalars(
            select(Message).where(Message.conversation_id == call.conversation_id, Message.role == "assistant")
        ).one()
        assert [st["label"] for st in answer.steps] == ["Checking: Weather in Lahore?"]
        # Both realtime responses plus the full Junior Muneer's lookup.
        assert answer.cost_usd == pytest.approx(call.cost_usd)
        assert answer.cost_usd > 2 * call_cost(usage_event()["response"]["usage"], {"audio_output": 20})

    app = create_app(model_provider=lambda: (lambda _n: model), realtime=FakeGateway)
    with TestClient(app) as client:
        summary = client.get(f"/api/conversations/{call.conversation_id}/summary").json()
    assert summary["kind"] == "call"
    assert summary["cost_usd"] == pytest.approx(call.cost_usd, rel=1e-3)
    assert summary["call_seconds"] is not None


def test_a_lookup_cut_off_by_hanging_up_still_shows_in_show_work():
    model = ScriptedModel([chunked_answer("Headline: ...")])
    call, _, _ = run_call(
        [
            heard("What's the news?"),
            said("Let me check."),
            usage_event(),
            tool("ask_junior", '{"question": "Top news in Pakistan?"}', "a1"),
            # call ends here, before he says the headline
        ],
        model,
    )
    with session_scope() as s:
        last = s.scalars(select(Message).where(Message.role == "assistant")).all()[-1]
        assert [st["label"] for st in last.steps] == ["Checking: Top news in Pakistan?"]
        assert last.cost_usd == pytest.approx(call.cost_usd)
