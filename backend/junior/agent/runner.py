"""Runs an agent for one turn and turns SDK stream events into simple chat events.

Events (plain dicts, sent to the dashboard as they happen):
    {"type": "delta", "text": "..."}                     a piece of the answer
    {"type": "step", "id", "kind", "label", "status"}    a tool or web search, running/done
    {"type": "final", "result": TurnResult}              last event (not sent as-is)
Tools may add their own events through TurnContext.pending_events.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import (
    Agent,
    RawResponsesStreamEvent,
    RunContextWrapper,
    RunHooks,
    Runner,
    RunItemStreamEvent,
)
from agents.items import ModelResponse, TResponseInputItem

from junior.agent.context import ModelUsage, TurnContext
from junior.costs import BudgetExceeded
from junior.models import ModelRouter

MAX_TURNS = 8

STEP_LABELS = {
    "web_search_call": "Searching the web",
    "recent_chats": "Looking at your recent chats",
    "search_chats": "Searching your past chats",
    "spending": "Checking your spending",
    "save_memory": "Saving a memory",
    "forget_memory": "Forgetting a memory",
}


@dataclass
class TurnResult:
    text: str
    usage: list[ModelUsage] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usage)


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


class CostHooks(RunHooks[TurnContext]):
    """Records the cost of every model call, notices web searches, and stops the
    run before a model call once the budget for this turn is used up."""

    def __init__(
        self, router: ModelRouter, model_names: dict[str, str], budget: float | None = None
    ) -> None:
        self.router = router
        self.model_names = model_names
        self.budget = budget

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        spent = sum(u.cost_usd for u in context.context.usage)
        if self.budget is not None and spent >= self.budget:
            raise BudgetExceeded(
                f"Stopped: this answer used up what was left of today's cap (${spent:.2f})."
            )

    async def on_llm_end(
        self, context: RunContextWrapper[TurnContext], agent: Agent[Any], response: ModelResponse
    ) -> None:
        searches = sum(1 for item in response.output if _get(item, "type") == "web_search_call")
        if searches:
            # Web results are outside text: no memory saving for the rest of this turn.
            context.context.mark_outside()
        u = response.usage
        cached = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
        model = self.model_names.get(agent.name, "unknown")
        cost = self.router.price(model).cost(u.input_tokens, u.output_tokens, cached)
        cost += searches * self.router.tool_prices.get("web_search", 0.0)
        context.context.usage.append(
            ModelUsage(
                agent=agent.name,
                model=model,
                input_tokens=u.input_tokens,
                cached_input_tokens=cached,
                output_tokens=u.output_tokens,
                web_searches=searches,
                cost_usd=cost,
            )
        )


def _web_search_step(item: Any) -> dict[str, Any] | None:
    if _get(item, "type") != "web_search_call":
        return None
    action = _get(item, "action")
    query = _get(action, "query") if action is not None else None
    label = STEP_LABELS["web_search_call"] + (f": {query}" if query else "")
    return {"id": _get(item, "id"), "kind": "web_search", "label": label}


def _function_step(raw: Any) -> dict[str, Any] | None:
    if _get(raw, "type") != "function_call":
        return None
    name = _get(raw, "name")
    return {
        "id": _get(raw, "call_id"),
        "kind": "tool",
        "name": name,
        "label": STEP_LABELS.get(name, f"Using {name}"),
        "status": "running",
    }


async def stream_turn(
    agent: Agent[TurnContext],
    model_name: str,
    router: ModelRouter,
    input_items: list[TResponseInputItem],
    context: TurnContext,
    budget: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    hooks = CostHooks(router, {agent.name: model_name}, budget)
    result = Runner.run_streamed(
        agent, input_items, context=context, hooks=hooks, max_turns=MAX_TURNS
    )
    steps: dict[str, dict[str, Any]] = {}
    text_parts: list[str] = []

    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if data.type == "response.output_text.delta" and data.delta:
                text_parts.append(data.delta)
                yield {"type": "delta", "text": data.delta}
            elif data.type in ("response.output_item.added", "response.output_item.done"):
                # Web search runs inside the model response: show it while it runs.
                step = _web_search_step(data.item)
                if step:
                    step = steps.setdefault(step["id"], step)
                    step["status"] = "running" if data.type.endswith("added") else "done"
                    yield {"type": "step", **step}
        elif isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                step = _function_step(event.item.raw_item)
                if step and step["id"] not in steps:
                    steps[step["id"]] = step
                    yield {"type": "step", **step}
            elif event.name == "tool_output":
                call_id = _get(event.item.raw_item, "call_id")
                if call_id in steps:
                    steps[call_id]["status"] = "done"
                    yield {"type": "step", **steps[call_id]}
        while context.pending_events:
            yield context.pending_events.pop(0)

    final = result.final_output
    text = final if isinstance(final, str) and final else "".join(text_parts)
    yield {
        "type": "final",
        "result": TurnResult(text=text, usage=context.usage, steps=list(steps.values())),
    }


async def run_once(
    agent: Agent[TurnContext],
    model_name: str,
    router: ModelRouter,
    input_items: list[TResponseInputItem],
    context: TurnContext,
    budget: float | None = None,
) -> TurnResult:
    """Run an agent without streaming (for background helpers like the summarizer)."""
    hooks = CostHooks(router, {agent.name: model_name}, budget)
    result = await Runner.run(
        agent, input_items, context=context, hooks=hooks, max_turns=MAX_TURNS
    )
    text = result.final_output if isinstance(result.final_output, str) else ""
    return TurnResult(text=text, usage=context.usage)
