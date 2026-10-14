import asyncio

import pytest

from fake_ai import (
    TEST_ROUTER,
    ScriptedModel,
    answer_after_web_search,
    chunked_answer,
    function_call,
    usage,
)
from junior.agent.builder import NoApiKeyError, build_agent, openai_model_provider
from junior.agent.context import TurnContext
from junior.agent.runner import stream_turn
from junior.db import init_db
from junior.registry import load_registry
from junior.settings_store import all_settings, set_setting


@pytest.fixture
def db():
    init_db()


def run(model: ScriptedModel, question: str, settings: dict | None = None):
    agent, model_name = build_agent(
        load_registry().get("junior_muneer"), TEST_ROUTER, lambda _name: model
    )
    context = TurnContext(conversation_id=None, settings=settings or all_settings())

    async def collect():
        return [
            e
            async for e in stream_turn(
                agent, model_name, TEST_ROUTER, [{"role": "user", "content": question}], context
            )
        ]

    events = asyncio.run(collect())
    return events, events[-1]["result"], context


def test_answer_streams_in_pieces_and_is_costed(db):
    model = ScriptedModel([chunked_answer("Hello Muneer! How are you today?", u=usage(1000, 100))])
    events, result, _ = run(model, "Hi")

    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert len(deltas) > 3
    assert "".join(deltas) == result.text == "Hello Muneer! How are you today?"
    # 1000 input at $2/M + 100 output at $10/M
    assert result.cost_usd == pytest.approx(0.002 + 0.001)
    assert result.usage[0].model == "fake-strong"
    model.assert_complete()


def test_instructions_have_name_language_and_personality(db):
    set_setting("user_name", "Ali")
    set_setting("language", "urdu")
    model = ScriptedModel([chunked_answer("ٹھیک ہوں")])
    run(model, "آپ کیسے ہیں؟")

    prompt = model.first_call.system_instructions
    assert "friend of Ali" in prompt
    assert "always reply in Urdu" in prompt
    assert "never pretend to be human" in prompt
    assert "{{" not in prompt  # every placeholder filled


def test_urdu_text_passes_through_unchanged(db):
    model = ScriptedModel([chunked_answer("میں ٹھیک ہوں، شکریہ!")])
    events, result, _ = run(model, "آپ کیسے ہیں؟")
    assert model.first_call.input[0]["content"] == "آپ کیسے ہیں؟"
    assert result.text == "میں ٹھیک ہوں، شکریہ!"


def test_web_search_shows_a_step_costs_extra_and_marks_outside_content(db):
    model = ScriptedModel(
        [answer_after_web_search("news today", "Here is today's news.", u=usage(1000, 100))]
    )
    events, result, context = run(model, "What's new today?")

    steps = [e for e in events if e["type"] == "step"]
    assert [s["status"] for s in steps] == ["running", "done"]
    assert steps[0]["label"] == "Searching the web: news today"
    assert result.usage[0].web_searches == 1
    assert result.cost_usd == pytest.approx(0.003 + 0.01)
    # Web results are outside text, so memory saving is blocked for this turn.
    assert context.outside_content_seen


def test_database_tool_answers_spending_question(db):
    model = ScriptedModel(
        [
            [function_call("spending", {"period": "today"}, call_id="c1")],
            chunked_answer("You spent nothing today."),
        ]
    )
    events, result, context = run(model, "How much did I spend today?")

    steps = [e for e in events if e["type"] == "step"]
    assert [(s["name"], s["status"]) for s in steps] == [
        ("spending", "running"),
        ("spending", "done"),
    ]
    tool_output = model.last_call.input[-1]["output"]
    assert "Spend (today): $0.0000" in tool_output
    assert "Daily safety cap: $5.00" in tool_output
    assert len(result.usage) == 2  # two model calls, both costed
    assert not context.outside_content_seen


def test_without_a_key_there_is_a_clear_message():
    with pytest.raises(NoApiKeyError, match="backend/.env"):
        openai_model_provider()


def test_web_search_is_delegated_to_the_cheap_researcher(db, monkeypatch):
    """The hosted search adds ~4,400 tokens to every request it's attached to, so only
    the small web_researcher has it; Junior Muneer calls it through a light tool."""
    from agents import WebSearchTool

    from junior.agent.helpers import HelperRunner

    names_used = []
    model = ScriptedModel(
        [
            [function_call("web_search", {"query": "Lahore weather"}, call_id="w1")],
            answer_after_web_search("Lahore weather", "- Sunny, 31°C (source: example.com)"),
            chunked_answer("It's sunny in Lahore, about 31°C."),
        ]
    )

    def provider(name):
        names_used.append(name)
        return model

    registry = load_registry()
    agent, model_name = build_agent(registry.get("junior_muneer"), TEST_ROUTER, provider)
    context = TurnContext(
        conversation_id=None, settings=all_settings(), helpers=HelperRunner(registry, provider)
    )

    async def collect():
        return [
            e
            async for e in stream_turn(
                agent, model_name, TEST_ROUTER, [{"role": "user", "content": "Weather?"}], context
            )
        ]

    import junior.agent.helpers as helpers_mod

    monkeypatch.setattr(helpers_mod, "get_router", lambda *a: TEST_ROUTER)  # test prices
    events = asyncio.run(collect())

    main_call, researcher_call, final_call = model.calls
    assert not any(isinstance(t, WebSearchTool) for t in main_call.tools)
    assert any(isinstance(t, WebSearchTool) for t in researcher_call.tools)
    assert researcher_call.input[0]["content"] == "Lahore weather"
    assert "Sunny, 31°C" in final_call.input[-1]["output"]
    assert names_used == ["fake-strong", "fake-small"]  # researcher on the small model

    steps = [e for e in events if e["type"] == "step"]
    assert steps[0]["label"] == "Searching the web: Lahore weather"
    result = events[-1]["result"]
    assert [u.agent for u in result.usage] == ["junior_muneer", "web_researcher", "junior_muneer"]
    assert result.usage[1].web_searches == 1
    assert context.outside_content_seen  # memory saving blocked for this turn
