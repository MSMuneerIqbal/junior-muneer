"""Runs an agent for one turn and turns SDK stream events into simple chat events.

Events (plain dicts, sent to the dashboard as they happen):
    {"type": "delta", "text": "..."}                     a piece of the answer
    {"type": "step", "id", "kind", "label", "status"}    a tool or web search, running/done
    {"type": "final", "result": TurnResult}              last event (not sent as-is)
Tools may add their own events through TurnContext.pending_events.
"""

import asyncio
import json
import re
import time
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
from junior.agent.style import no_emojis, talk_mode
from junior.audit import audit
from junior.costs import BudgetExceeded
from junior.models import ModelRouter

ALIVE_SECONDS = 5  # at most one "still writing" signal this often
MAX_TURNS = 12  # a request with several parts: a checklist, the parts, checklist updates, the answer

STEP_LABELS = {
    "web_search_call": "Searching the web",
    "recent_chats": "Looking at your recent chats",
    "search_chats": "Searching your past chats",
    "spending": "Checking your spending",
    "pc_list": "Looking in a folder on your PC",
    "pc_find": "Searching your PC",
    "pc_read": "Reading a file on your PC",
    "pc_write": "Preparing a file change",
    "pc_make_folder": "Preparing a new folder",
    "pc_move": "Preparing a move",
    "pc_delete": "Preparing a delete (to the Recycle Bin)",
    "pc_run": "Preparing a command",
    "browser_snapshot": "Reading the browser page",
    "browser_action": "Preparing a browser action for approval",
    "ask_computer_agent": "Asking the Computer Agent",
    "ask_browser_agent": "Asking the Browser Agent",
    "save_memory": "Saving a memory",
    "forget_memory": "Forgetting a memory",
    "recall_memory": "Looking through your memories",
    "add_to_approvals": "Adding it to your approval queue",
    "write_draft": "Writing it with the team",
    "social_media": "Asking the Social Media Manager",
    "ai_news": "Asking the AI-News-Agent",
    "freelance": "Asking the Freelance Manager",
    "score_job": "Scoring the job",
    "save_order": "Saving the order",
    "update_order": "Updating the order",
    "pakistan_news": "Asking the Social-News-Agent",
    "save_ideas": "Saving ideas",
    "run_in_background": "Starting it in the background",
    "what_happened": "Checking what happened",
    "my_feeds": "Reading your feeds",
    "use_skill": "Loading task instructions",
    "save_skill": "Preparing a skill for review",
    "read_skill_resource": "Reading a skill resource",
    "ask_documents_agent": "Delegating research and document work",
    "ask_code_agent": "Preparing a reviewed code proposal",
    "code_files": "Listing editable source files",
    "code_read": "Reading a tracked source file",
    "code_review": "Preparing a code-operation review",
    "task_status": "Checking task progress",
    "make_class_notes": "Preparing your saved class notes",
    "place_document": "Preparing the file's destination",
    "find_saved_files": "Finding saved files",
    "save_text_to_library": "Saving the original text",
    "share_drive_file": "Preparing the Drive sharing permission",
    "zip_folder": "Packaging the folder as ZIP",
    "find_class_notes": "Finding your class notes",
    "read_class_note": "Reading saved class notes",
    "list_note_folders": "Looking at your Notes folders",
}


@dataclass
class TurnResult:
    text: str
    usage: list[ModelUsage] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    # A helper's structured answer (an agent with an output type).
    output: Any = None

    @property
    def cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usage)


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


class TurnHooks(RunHooks[TurnContext]):
    """Records the cost of every model call, notices web searches, logs tool calls
    to the audit log, and stops the run before a model call once the budget for
    this turn is used up."""

    def __init__(
        self, router: ModelRouter, model_names: dict[str, str], budget: float | None = None
    ) -> None:
        self.router = router
        self.model_names = model_names
        self.budget = budget

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        context.context.check_task_limits()
        if context.context.task_id is not None:
            context.context.task_model_calls += 1
        elif not context.context.memory_locked:
            cap = context.context.settings.get("chat_max_model_calls", 16)
            if context.context.chat_model_calls >= cap:
                raise BudgetExceeded(f"Stopped: this reply reached its limit of {cap} AI calls, including helpers. Continue with a new message or adjust Settings → Budget.")
            context.context.chat_model_calls += 1
        spent = sum(u.cost_usd for u in context.context.usage)
        allowance = self.budget
        if context.context.task_id is None and not context.context.memory_locked:
            allowance = min(allowance if allowance is not None else float("inf"), context.context.settings.get("chat_budget_usd", .5))
        if allowance is not None and spent >= allowance:
            raise BudgetExceeded(
                f"Stopped: this answer reached its cost cap (${spent:.2f} used, ${allowance:.2f} allowance)."
            )

    async def on_llm_end(
        self, context: RunContextWrapper[TurnContext], agent: Agent[Any], response: ModelResponse
    ) -> None:
        searches = [item for item in response.output if _get(item, "type") == "web_search_call"]
        from junior.documents.sources import collect_response_sources
        collect_response_sources(context.context, response.output)
        if searches:
            # Web results are outside text: no memory saving for the rest of this turn.
            context.context.mark_outside()
        for item in searches:
            action = _get(item, "action")
            audit(
                "web_search",
                "web_search",
                detail={"query": _get(action, "query") if action is not None else None},
                cost_usd=self.router.tool_prices.get("web_search", 0.0),
                conversation_id=context.context.conversation_id,
            )
        searches = len(searches)
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
        if context.context.task_id is not None:
            from junior.background import progress
            progress(context.context.task_id, "", 0, context.context)

    async def on_tool_start(self, context, agent, tool) -> None:
        context.context.check_task_limits()

    async def on_tool_end(
        self, context: RunContextWrapper[TurnContext], agent: Agent[Any], tool: Any, result: object
    ) -> None:
        text = str(result)
        audit(
            "tool_call",
            getattr(tool, "name", type(tool).__name__),
            result="pending" if text.startswith("NOT done yet - waiting for their OK") else "refused" if text.startswith("NOT ") else "error" if text.startswith("ERROR: the tool failed") else "ok",
            detail={"agent": agent.name, **_tool_log_detail(context, result)},
            conversation_id=context.context.conversation_id,
        )


def _tool_log_detail(context: Any, result: object) -> dict[str, Any]:
    return {
        "arguments": getattr(context, "tool_arguments", None),
        "result": str(result),
    }


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
    if name == "update_plan":  # shown as the checklist itself, not as a step
        return None
    label = STEP_LABELS.get(name, f"Using {name}")
    if name == "web_search":
        try:
            label = f"Searching the web: {json.loads(_get(raw, 'arguments') or '{}')['query']}"
        except (ValueError, KeyError, TypeError):
            label = STEP_LABELS["web_search_call"]
    return {
        "id": _get(raw, "call_id"),
        "kind": "web_search" if name == "web_search" else "tool",
        "name": name,
        "label": label,
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
    hooks = TurnHooks(router, {agent.name: model_name}, budget)
    result = Runner.run_streamed(
        agent, input_items, context=context, hooks=hooks, max_turns=20 if agent.name == "browser_agent" else MAX_TURNS
    )
    steps: dict[str, dict[str, Any]] = {}
    text_parts: list[str] = []
    # Junior mode is professional: no emojis. As a friend he may use a few.
    clean = no_emojis if talk_mode(context.user_text) == "junior" else (lambda text: text)

    def pending() -> list[dict[str, Any]]:
        out = []
        while context.pending_events:
            event = context.pending_events.pop(0)
            if event.get("type") == "step":  # steps from inside a tool are kept for Show work
                steps[event["id"]] = {k: v for k, v in event.items() if k != "type"}
            out.append(event)
        return out

    last_alive = time.monotonic()
    async for event in _with_tool_events(result.stream_events(), context):
        if event is None:  # a tool emitted something mid-run
            for e in pending():
                yield e
            continue
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if data.type == "response.output_text.delta" and data.delta:
                piece = clean(data.delta)  # Junior mode: no emojis (agent/style.py)
                text_parts.append(piece)
                if piece:
                    yield {"type": "delta", "text": piece}
            elif data.type in ("response.output_item.added", "response.output_item.done"):
                # Web search runs inside the model response: show it while it runs.
                step = _web_search_step(data.item)
                if step:
                    step = steps.setdefault(step["id"], step)
                    step["status"] = "running" if data.type.endswith("added") else "done"
                    yield {"type": "step", **step}
            elif time.monotonic() - last_alive > ALIVE_SECONDS:
                # The model is still writing something we don't show (e.g. a long tool call, like a whole Google
                # Doc): tell the chat it's alive, so its "silent for 60 s" check doesn't give up on it.
                last_alive = time.monotonic()
                yield {"type": "alive"}
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
        for e in pending():
            yield e

    final = result.final_output
    text = clean(final) if isinstance(final, str) and final else "".join(text_parts)
    text = re.sub(r"[ \t]{2,}", " ", text).replace(" \n", "\n")
    yield {
        "type": "final",
        "result": TurnResult(text=text, usage=context.usage, steps=list(steps.values())),
    }


async def _with_tool_events(stream: AsyncIterator[Any], context: TurnContext) -> AsyncIterator[Any]:
    """The SDK's events, plus None whenever a tool emits an event, so long tools show progress."""
    iterator = stream.__aiter__()
    next_event: asyncio.Task | None = None
    try:
        while True:
            if next_event is None:
                next_event = asyncio.ensure_future(iterator.__anext__())
            context.wake.clear()
            if context.pending_events:
                yield None
            woke = asyncio.ensure_future(context.wake.wait())
            done, _ = await asyncio.wait({next_event, woke}, return_when=asyncio.FIRST_COMPLETED)
            if woke not in done:
                woke.cancel()
            if next_event in done:
                try:
                    event = next_event.result()
                except StopAsyncIteration:
                    return
                next_event = None
                yield event
            else:
                yield None
    finally:
        if next_event is not None and not next_event.done():
            next_event.cancel()


async def run_once(
    agent: Agent[TurnContext],
    model_name: str,
    router: ModelRouter,
    input_items: list[TResponseInputItem],
    context: TurnContext,
    budget: float | None = None,
) -> TurnResult:
    """Run an agent without streaming (for background helpers like the summarizer)."""
    hooks = TurnHooks(router, {agent.name: model_name}, budget)
    result = await Runner.run(
        agent, input_items, context=context, hooks=hooks, max_turns=20 if agent.name == "browser_agent" else MAX_TURNS
    )
    text = result.final_output if isinstance(result.final_output, str) else ""
    return TurnResult(text=text, usage=context.usage, output=result.final_output)
