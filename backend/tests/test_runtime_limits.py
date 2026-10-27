"""Shared model quotas, preflight/output limits, cumulative usage and zero-cost session/local operations."""

import asyncio

import pytest
from agents import Agent, ModelSettings, RunContextWrapper, WebSearchTool
from agents.testing import ModelStep
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call, usage
from junior.agent.context import ModelUsage, TurnContext
from junior.agent.runner import TurnHooks
from junior.costs import BudgetExceeded
from junior.documents.limits import TaskModel, task_provider
from junior.main import create_app
from junior.models import get_router
from junior.settings_store import all_settings, set_setting
from test_chat import chat


def context():
    return TurnContext(conversation_id=None, settings=all_settings())


def test_model_calls_are_shared_across_helpers_and_stop_before_extra_requests():
    ctx = context()
    ctx.settings["chat_max_model_calls"] = 2
    wrapper = RunContextWrapper(ctx)
    hooks = TurnHooks(get_router(), {}, .5)
    async def run():
        await hooks.on_llm_start(wrapper, Agent(name="junior"), "", [])
        await hooks.on_llm_start(wrapper, Agent(name="helper"), "", [])
        with pytest.raises(BudgetExceeded, match="2 AI calls"):
            await hooks.on_llm_start(wrapper, Agent(name="fallback"), "", [])
    asyncio.run(run())
    assert ctx.chat_model_calls == 2


def test_response_budget_accounts_for_usage_tools_and_full_schema_before_calling():
    ctx = context()
    ctx.settings["chat_budget_usd"] = .03
    ctx.settings["max_output_tokens"] = 700
    name = get_router().tiers["strong"]
    model = TaskModel(ScriptedModel(), name, ctx)
    settings = model.settings_for("small", [], ModelSettings(), [], None)
    assert 512 <= settings.max_tokens <= 700
    class LargeSchema:
        def json_schema(self):
            return {"description": "x" * 100_000}
    with pytest.raises(BudgetExceeded, match="allowance"):
        model.settings_for("small", [], ModelSettings(), [], LargeSchema())
    ctx.usage.append(ModelUsage("helper", name, 10, 0, 10, 0, .029))
    with pytest.raises(BudgetExceeded):
        model.settings_for("small", [], ModelSettings(), [], None)
    assert not model.model.calls
    ctx.usage.clear()
    ctx.settings["chat_budget_usd"] = .5
    bounded = model.settings_for("small", [], ModelSettings(), [WebSearchTool()], None)
    assert bounded.extra_args["max_tool_calls"] == 1


def test_provider_is_not_double_wrapped_and_chat_retry_policy_is_preserved():
    ctx = context()
    model = ScriptedModel()
    bounded = task_provider(lambda name: model, ctx)
    first = bounded("gpt-6.1-sol")
    second = task_provider(lambda name: first, ctx)("gpt-6.1-sol")
    assert first is second and first.model is model


def test_helper_hits_shared_chat_quota_without_external_search_or_extra_model_calls():
    set_setting("chat_max_model_calls", 1)
    model = ScriptedModel()
    model.enqueue(ModelStep(output=[function_call("web_search", {"query": "synthetic test"}, call_id="search")], usage=usage()))
    with TestClient(create_app(model_provider=lambda: lambda name: model)) as client:
        result = chat(client, "Search for a synthetic testing example")[-1]
        assert result["type"] == "error" and "limit of 1 AI calls" in result["message"]
        assert len(model.calls) == 1
        assert client.get("/api/usage/today").json()["spent_usd"] > 0


def test_clear_keeps_spend_and_local_commands_work_after_budget_is_exhausted():
    model = ScriptedModel([chunked_answer("Synthetic answer", u=usage())])
    with TestClient(create_app(model_provider=lambda: lambda name: model)) as client:
        first = chat(client, "Hello")[-1]
        assert first["type"] == "done"
        spent = client.get("/api/usage/today").json()["spent_usd"]
        reset = chat(client, "/clear", first["conversation_id"])[-1]
        assert reset["cost_usd"] == 0 and reset["conversation_id"] != first["conversation_id"]
        assert client.get("/api/usage/today").json()["spent_usd"] == spent
        set_setting("daily_cap_usd", 0)
        for command in ("/skills", "/memory", "/reload-skills", "/update --status"):
            result = chat(client, command)[-1]
            assert result["type"] == "done" and result["cost_usd"] == 0
        assert len(model.calls) == 1


@pytest.mark.parametrize("body", [{"chat_budget_usd": -1}, {"chat_budget_usd": "NaN"}, {"chat_max_model_calls": 25}, {"max_output_tokens": 100000}])
def test_invalid_limits_are_rejected_without_changing_current_settings(body):
    with TestClient(create_app()) as client:
        before = client.get("/api/settings").json()
        assert client.patch("/api/settings", json=body).status_code == 422
        after = client.get("/api/settings").json()
        assert all(after[key] == before[key] for key in body)


def test_runtime_limits_status_is_local_and_matches_effective_settings():
    with TestClient(create_app()) as client:
        client.patch("/api/settings", json={"chat_budget_usd": .2, "chat_max_model_calls": 5, "max_output_tokens": 2048}).raise_for_status()
        limits = client.get("/api/usage/limits").json()
        assert limits["chat"] == {"budget_usd": .2, "model_calls": 5, "seconds": 600, "output_tokens": 2048, "transport_retries": 1}
        assert limits["computer"]["desktop_snapshots"] == 4 and limits["computer"]["browser_snapshots"] == 6
        assert limits["maintenance"]["retries"] == 0


def test_insufficient_remaining_daily_budget_prevents_even_the_first_request():
    set_setting("daily_cap_usd", .001)
    model = ScriptedModel([chunked_answer("must not be requested")])
    with TestClient(create_app(model_provider=lambda: lambda name: model)) as client:
        result = chat(client, "Hello")[-1]
        assert result["type"] == "error" and "allowance" in result["message"]
        assert not model.calls
        assert client.get("/api/usage/today").json()["spent_usd"] == 0
