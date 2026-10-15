"""Live calls: a hands-free, real-time voice conversation with Junior Muneer.

How a call works (OpenAI's Realtime API over WebRTC, "unified" set-up):
  1. The browser makes a WebRTC offer and sends it to POST /api/call/start.
  2. The backend creates the call at OpenAI with Junior Muneer's personality,
     memories, voice and tools, and returns the answer. The browser never sees
     any API key, not even a short-lived one.
  3. The backend stays attached to the call: it saves both sides of the
     conversation as a chat, runs the tools (same safety rules as the chat),
     records the cost of every response, and ends the call at the daily cap
     or the daily call-minutes limit.

    POST /api/call/start   {"sdp": "..."} -> {"sdp", "call_id", "conversation_id"}
    POST /api/call/end     {"call_id": "..."}
    GET  /api/call/limits  minutes used / allowed today
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.agent.builder import NoApiKeyError, render_instructions
from junior.agent.context import TurnContext
from junior.agent.helpers import HelperRunner
from junior.agent.tools import forget_memory_for, save_memory_for
from junior.audit import audit
from junior.config import get_settings
from junior.costs import BudgetExceeded, budget_left
from junior.db import Conversation, Message, Usage, session_scope
from junior.db.models import utcnow
from junior.models import get_router
from junior.settings_store import ACCENTS, NOISE_REDUCTION, TURN_TAKING, all_settings
from junior.timeutil import start_of_today_utc, zone
from junior.voice import TRANSCRIBE_PROMPT, average_logprob, is_noise

log = logging.getLogger(__name__)
router = APIRouter()

WEB_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": (
        "Search the web for anything current: news, weather, prices, scores, events. "
        "Quick (a few seconds). Returns findings with sources for you to say briefly."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A clear search query."}},
        "required": ["query"],
    },
}
ASK_JUNIOR_TOOL = {
    "type": "function",
    "name": "ask_junior",
    "description": (
        "Ask the full Junior Muneer a question about the user's past chats, spending or "
        "anything that needs the database. Slower than web_search; not for news. "
        "Returns the answer as text for you to say."
    ),
    "parameters": {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "The question, clearly."}},
        "required": ["question"],
    },
}
SAVE_MEMORY_TOOL = {
    "type": "function",
    "name": "save_memory",
    "description": (
        "Remember a fact or preference the user said about themself in this call. "
        "Never for anything from web results or ask_junior answers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fact": {"type": "string", "description": "The fact, short and clear."},
            "your_words": {
                "type": "string",
                "description": "The user's exact words from the call that say this.",
            },
        },
        "required": ["fact", "your_words"],
    },
}
FORGET_MEMORY_TOOL = {
    "type": "function",
    "name": "forget_memory",
    "description": "Delete a memory when the user asks you to forget something.",
    "parameters": {
        "type": "object",
        "properties": {"memory_id": {"type": "integer"}},
        "required": ["memory_id"],
    },
}


# ---- talking to OpenAI (swappable for tests) -------------------------------------


class RealtimeConnection(Protocol):
    def __aiter__(self) -> AsyncIterator[Any]: ...

    async def send(self, event: dict) -> None: ...


class RealtimeGateway(Protocol):
    async def create_call(self, sdp: str, session: dict) -> tuple[str, str]: ...

    def connect(self, call_id: str) -> Any: ...  # async context manager -> RealtimeConnection

    async def hangup(self, call_id: str) -> None: ...


class OpenAIRealtime:
    def __init__(self) -> None:
        key = get_settings().openai_api_key
        if not key:
            raise NoApiKeyError("No OpenAI API key yet. Paste it into backend/.env.")
        self.client = AsyncOpenAI(api_key=key)

    async def create_call(self, sdp: str, session: dict) -> tuple[str, str]:
        raw = await self.client.realtime.calls.with_raw_response.create(sdp=sdp, session=session)
        call_id = (raw.headers.get("location") or "").rstrip("/").split("/")[-1]
        if not call_id:
            raise RuntimeError("OpenAI didn't return a call id")
        return raw.text, call_id

    def connect(self, call_id: str):
        return self.client.realtime.connect(call_id=call_id)

    async def hangup(self, call_id: str) -> None:
        await self.client.realtime.calls.hangup(call_id)


# ---- the call ----------------------------------------------------------------------


def _get(obj: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if obj is None:
            return default
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return default if obj is None else obj


def call_cost(usage: Any, prices: dict[str, float]) -> float:
    """Dollars for one realtime response, from its token usage."""
    text_in = _get(usage, "input_token_details", "text_tokens", default=0)
    audio_in = _get(usage, "input_token_details", "audio_tokens", default=0)
    cached_text = _get(usage, "input_token_details", "cached_tokens_details", "text_tokens", default=0)
    cached_audio = _get(
        usage, "input_token_details", "cached_tokens_details", "audio_tokens", default=0
    )
    text_out = _get(usage, "output_token_details", "text_tokens", default=0)
    audio_out = _get(usage, "output_token_details", "audio_tokens", default=0)
    return (
        max(text_in - cached_text, 0) * prices.get("text_input", 0)
        + cached_text * prices.get("text_cached_input", 0)
        + max(audio_in - cached_audio, 0) * prices.get("audio_input", 0)
        + cached_audio * prices.get("audio_cached_input", 0)
        + text_out * prices.get("text_output", 0)
        + audio_out * prices.get("audio_output", 0)
    ) / 1_000_000


def call_seconds_today(tz_name: str) -> float:
    since = start_of_today_utc(tz_name)
    with session_scope() as s:
        rows = s.scalars(
            select(Usage.extra).where(Usage.agent == "live_call", Usage.created_at >= since)
        ).all()
    return sum(float(extra.get("seconds", 0)) for extra in rows)


@dataclass
class LiveCall:
    call_id: str
    conversation_id: int
    model: str
    context: TurnContext
    started: float = field(default_factory=time.monotonic)
    ended: bool = False
    end_reason: str = ""
    responses: int = 0
    cost_usd: float = 0.0
    task: asyncio.Task | None = None
    instructions: str = ""
    language: str = "english"  # the language of what you said last
    tools_running: int = 0
    current_response: str | None = None  # his reply being made right now
    dropped_responses: set = field(default_factory=set)  # replies to noise, cancelled
    filler_ids: set = field(default_factory=set)  # short "still looking" responses
    filler_done: asyncio.Event = field(default_factory=asyncio.Event)
    tool_tasks: set = field(default_factory=set)
    # For Show work on each spoken answer: tools used and cost not yet shown.
    pending_steps: list[dict] = field(default_factory=list)
    pending_cost: float = 0.0
    answer_in_response: int | None = None  # the answer saved during the current response


class CallManager:
    """Keeps track of live calls and runs the backend side of each."""

    def __init__(self, gateway_factory, registry, model_provider) -> None:
        self.gateway_factory = gateway_factory
        self.registry = registry
        self.model_provider = model_provider
        self.calls: dict[str, LiveCall] = {}

    # -- start -----------------------------------------------------------------

    def call_instructions(self, settings: dict) -> str:
        """His speech-first personality (agents/junior_muneer_voice.md)."""
        spec = self.registry.get("junior_muneer_voice")
        accent = ACCENTS.get(settings.get("voice_accent", "pakistani"), ACCENTS["pakistani"])
        return render_instructions(spec, settings).replace("{{accent}}", accent)

    def session_config(self, settings: dict, model: str) -> dict:
        instructions = self.call_instructions(settings)
        model_router = get_router()
        return {
            "type": "realtime",
            "model": model,
            "instructions": instructions,
            "audio": {
                "input": {
                    "transcription": {
                        "model": model_router.audio_model("transcribe"),
                        "prompt": TRANSCRIBE_PROMPT.format(name=settings["user_name"]),
                    },
                    # Semantic turn detection: he answers when you've finished your thought,
                    # not at every pause. He starts right away (no waiting for the
                    # transcript), and you can interrupt him any time.
                    "turn_detection": {
                        "type": "semantic_vad",
                        "eagerness": TURN_TAKING.get(settings.get("turn_taking"), "auto"),
                        "interrupt_response": True,
                        "create_response": True,
                    },
                    # Noise reduction suited to your microphone (Settings).
                    "noise_reduction": (
                        {"type": NOISE_REDUCTION[settings.get("mic_type", "headset")]}
                        if NOISE_REDUCTION.get(settings.get("mic_type", "headset"))
                        else None
                    ),
                },
                "output": {"voice": settings["tts_voice"], "speed": float(settings["tts_speed"])},
            },
            "tools": [WEB_SEARCH_TOOL, ASK_JUNIOR_TOOL, SAVE_MEMORY_TOOL, FORGET_MEMORY_TOOL],
            "tool_choice": "auto",
            # How sure the transcription is of each word: used to ignore breathing and noise.
            "include": ["item.input_audio_transcription.logprobs"],
        }

    async def start(self, sdp: str) -> tuple[LiveCall, str]:
        settings = all_settings()
        budget_left(settings)  # raises BudgetExceeded
        limit = float(settings["call_minutes_per_day"]) * 60
        if call_seconds_today(settings["timezone"]) >= limit:
            raise CallLimitReached(
                f"Today's live-call limit ({settings['call_minutes_per_day']} minutes) is used up. "
                "You can raise it in Settings, or keep chatting by text or voice messages."
            )
        gateway = self.gateway_factory()
        model = get_router().audio_model(
            "realtime_economy" if settings.get("call_quality") == "economy" else "realtime"
        )
        session = self.session_config(settings, model)
        answer, call_id = await gateway.create_call(sdp, session)

        local = datetime.now(zone(settings["timezone"]))
        with session_scope() as s:
            convo = Conversation(title=f"Live call · {local:%d %b %H:%M}", kind="call")
            s.add(convo)
            s.flush()
            conversation_id = convo.id
        context = TurnContext(
            conversation_id=conversation_id,
            settings=settings,
            helpers=HelperRunner(self.registry, self.model_provider()),
        )
        call = LiveCall(
            call_id=call_id,
            conversation_id=conversation_id,
            model=model,
            context=context,
            instructions=session["instructions"],
        )
        self.calls[call_id] = call
        call.task = asyncio.create_task(self._run(call, gateway, limit))
        audit("agent_run", "live_call", result="ok", detail={"event": "started", "model": model},
              conversation_id=conversation_id)
        return call, answer

    # -- the backend side of the call ------------------------------------------

    async def _run(self, call: LiveCall, gateway: RealtimeGateway, limit_seconds: float) -> None:
        used_before = call_seconds_today(call.context.settings["timezone"])
        watchdog = asyncio.create_task(self._watchdog(call, gateway, limit_seconds - used_before))
        try:
            async with gateway.connect(call.call_id) as conn:
                log.info("Attached to live call %s", call.call_id)
                async for event in conn:
                    log.debug("Call %s event: %s", call.call_id, _get(event, "type"))
                    await self.handle(call, conn, gateway, event)
                    if call.ended:
                        break
        except Exception as e:
            if not call.ended:
                log.exception("Live call %s stopped", call.call_id)
                call.end_reason = call.end_reason or f"connection lost: {type(e).__name__}"
        finally:
            watchdog.cancel()
            call.ended = True
            if call.tool_tasks:  # let running tools finish so their cost is recorded
                await asyncio.wait(list(call.tool_tasks), timeout=TOOL_FINISH_SECONDS)
                for task in list(call.tool_tasks):
                    task.cancel()
            self._finish(call)

    async def _watchdog(self, call: LiveCall, gateway: RealtimeGateway, seconds_left: float):
        """Ends the call when today's call minutes run out."""
        await asyncio.sleep(max(seconds_left, 0))
        await self.end(call.call_id, "daily call-minutes limit reached", gateway)

    async def handle(self, call: LiveCall, conn, gateway: RealtimeGateway, event: Any) -> None:
        kind = _get(event, "type", default="")
        if kind == "conversation.item.input_audio_transcription.completed":
            text = (_get(event, "transcript", default="") or "").strip()
            log.info(
                "Call %s heard %r (confidence %s)",
                call.call_id,
                text[:60],
                average_logprob(_get(event, "logprobs")),
            )
            if is_noise(text, _get(event, "logprobs")):
                # Breathing, a cough or background noise: stop any reply to it, and
                # take it out of the conversation.
                log.info("Call %s: ignored noise %r", call.call_id, text[:40])
                await self._drop_noise(call, conn, _get(event, "item_id"))
            else:
                message_id = self._save(call, "user", text)
                call.context.user_message_ids.append(message_id)
                call.context.outside_content_seen = False  # a new turn of yours
                language = spoken_language(text)
                if language != call.language:
                    # You switched language: tell him, for the rest of the call.
                    call.language = language
                    await conn.send(
                        {
                            "type": "session.update",
                            "session": {
                                "type": "realtime",
                                "instructions": call.instructions + LANGUAGE_NOTES[language],
                            },
                        }
                    )
        elif kind == "response.created":
            if _get(event, "response", "metadata", "kind") == "filler":
                call.filler_ids.add(_get(event, "response", "id"))
            else:
                call.current_response = _get(event, "response", "id")
        elif kind == "response.output_audio_transcript.done":
            text = (_get(event, "transcript", default="") or "").strip()
            if _get(event, "response_id") in call.filler_ids | call.dropped_responses:
                pass  # "still looking…" and replies to noise aren't part of the conversation
            elif text:
                text = await self._in_urdu_script(call, text)
                call.answer_in_response = self._save(
                    call, "assistant", text, steps=call.pending_steps, cost=call.pending_cost
                )
                call.pending_steps, call.pending_cost = [], 0.0
        elif kind == "response.function_call_arguments.done":
            # Run the tool in the background, so the call keeps going (and he can
            # say "still looking…") while it works.
            task = asyncio.create_task(self._tool_then_reply(call, conn, event))
            call.tool_tasks.add(task)
            task.add_done_callback(call.tool_tasks.discard)
        elif kind == "response.done" and _get(event, "response", "id") in call.filler_ids:
            call.filler_ids.discard(_get(event, "response", "id"))
            call.filler_done.set()
            usage = _get(event, "response", "usage")
            if usage is not None:
                cost = call_cost(usage, get_router().audio_price(call.model))
                call.cost_usd += cost
                call.pending_cost += cost
                self._record_call_usage(call, usage, cost)
        elif kind == "response.done":
            usage = _get(event, "response", "usage")
            if usage is not None:
                cost = call_cost(usage, get_router().audio_price(call.model))
                call.responses += 1
                call.cost_usd += cost
                self._add_cost(call, cost)
                self._record_call_usage(call, usage, cost)
                try:
                    budget_left(call.context.settings)
                except BudgetExceeded:
                    await self.end(call.call_id, "daily cost cap reached", gateway)
        elif kind == "error":
            log.warning("Realtime error on call %s: %s", call.call_id, _get(event, "error"))

    def _record_call_usage(self, call: LiveCall, usage: Any, cost: float) -> None:
        with session_scope() as s:
            s.add(
                Usage(
                    agent="junior_muneer_live",
                    model=call.model,
                    mode="call",
                    conversation_id=call.conversation_id,
                    input_tokens=_get(usage, "input_tokens", default=0),
                    cached_input_tokens=_get(usage, "input_token_details", "cached_tokens", default=0),
                    output_tokens=_get(usage, "output_tokens", default=0),
                    cost_usd=cost,
                )
            )

    async def _tool_then_reply(self, call: LiveCall, conn, event: Any) -> None:
        call.tools_running += 1
        filler = asyncio.create_task(self._fillers(call, conn))
        try:
            output = await self.run_tool(
                call, _get(event, "name"), _get(event, "arguments", default="{}")
            )
        finally:
            call.tools_running -= 1
            filler.cancel()
        if call.ended:
            return
        if call.filler_ids:  # let a "still looking…" finish before the real answer
            call.filler_done.clear()
            try:
                await asyncio.wait_for(call.filler_done.wait(), FILLER_WAIT_SECONDS)
            except TimeoutError:
                pass
        await conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": _get(event, "call_id"),
                    "output": output,
                },
            }
        )
        await conn.send(self.reply_request(call))

    async def _fillers(self, call: LiveCall, conn) -> None:
        """While a tool runs, say a short "still looking…" now and then."""
        await asyncio.sleep(FILLER_FIRST_SECONDS)
        while call.tools_running and not call.ended:
            if not call.filler_ids:
                await conn.send(
                    {
                        "type": "response.create",
                        "response": {
                            "conversation": "none",  # not part of the conversation
                            "metadata": {"kind": "filler"},
                            "instructions": call.instructions
                            + LANGUAGE_NOTES[call.language]
                            + FILLER_NOTE,
                        },
                    }
                )
            await asyncio.sleep(FILLER_EVERY_SECONDS)

    def reply_request(self, call: LiveCall) -> dict:
        """Let him carry on talking (after a tool)."""
        return {"type": "response.create"}

    async def _drop_noise(self, call: LiveCall, conn, item_id: str | None) -> None:
        if call.current_response:
            call.dropped_responses.add(call.current_response)
            await conn.send({"type": "response.cancel", "response_id": call.current_response})
            await conn.send({"type": "output_audio_buffer.clear"})
        if item_id:
            await conn.send({"type": "conversation.item.delete", "item_id": item_id})

    async def run_tool(self, call: LiveCall, name: str | None, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except ValueError:
            return "Invalid arguments."
        context = call.context
        if name == "web_search":
            result = await self._quick_search(call, str(args.get("query", "")))
        elif name == "save_memory":
            result = save_memory_for(context, str(args.get("fact", "")), str(args.get("your_words", "")))
        elif name == "forget_memory":
            result = forget_memory_for(context, int(args.get("memory_id", 0)))
        elif name == "ask_junior":
            result = await self._ask_junior(call, str(args.get("question", "")))
        else:
            result = f"Unknown tool {name!r}."
        context.pending_events.clear()
        label = {
            "web_search": f"Searching the web: {args.get('query', '')}",
            "ask_junior": f"Checking: {args.get('question', '')}",
            "save_memory": "Saving a memory",
            "forget_memory": "Forgetting a memory",
        }.get(name or "", f"Using {name}")
        call.pending_steps.append(
            {
                "id": f"call-tool-{len(call.pending_steps)}-{name}",
                "kind": "web_search" if name in ("web_search", "ask_junior") else "tool",
                "name": name,
                "label": label,
                "status": "done",
            }
        )
        audit(
            "tool_call",
            name or "?",
            result="refused" if result.startswith("NOT ") else "ok",
            detail={"agent": "junior_muneer_live", "arguments": arguments, "result": result},
            conversation_id=call.conversation_id,
        )
        return result

    async def _in_urdu_script(self, call: LiveCall, text: str) -> str:
        """If you spoke Urdu but his words came back in Latin letters (Roman Urdu),
        rewrite them in Urdu script before saving, so the chat reads right."""
        if call.language != "urdu" or not is_roman(text) or call.context.helpers is None:
            return text
        context = call.context
        spent_before = len(context.usage)
        try:
            rewritten = (await context.helpers.run("urdu_script", text, context)).strip()
        except Exception:
            log.exception("Rewriting a call reply in Urdu script failed; keeping it as is")
            return text
        new_usage = context.usage[spent_before:]
        call.pending_cost += sum(u.cost_usd for u in new_usage)
        call.cost_usd += sum(u.cost_usd for u in new_usage)
        with session_scope() as s:
            from junior.chat.history import save_usage

            save_usage(s, new_usage, call.conversation_id, None, mode="call")
        return rewritten if rewritten and not is_roman(rewritten) else text

    async def _quick_search(self, call: LiveCall, query: str) -> str:
        """Straight to the web researcher (small model, one quick search): ~4 seconds."""
        if not query.strip():
            return "No search query given."
        context = call.context
        context.mark_outside()  # web results: no memory saving this turn
        spent_before = len(context.usage)
        try:
            text = await context.helpers.run("web_researcher", query, context)
        except BudgetExceeded as e:
            return f"Can't search: {e}"
        new_usage = context.usage[spent_before:]
        call.pending_cost += sum(u.cost_usd for u in new_usage)
        call.cost_usd += sum(u.cost_usd for u in new_usage)
        with session_scope() as s:
            from junior.chat.history import save_usage

            save_usage(s, new_usage, call.conversation_id, None, mode="call")
        return text or "Nothing reliable found."

    async def _ask_junior(self, call: LiveCall, question: str) -> str:
        """The full Junior Muneer (web search, database) answers a question for the call."""
        from junior.agent.builder import build_agent, chosen_model
        from junior.agent.runner import run_once

        if not question.strip():
            return "No question given."
        context = call.context
        context.mark_outside()  # the answer may include web results
        spent_before = len(context.usage)
        router_ = get_router()
        spec = self.registry.get("junior_muneer")
        # Calls never wait on other providers (DeepSeek): use the OpenAI default.
        model = router_.model_for("junior_muneer", spec.model)
        if router_.provider_of(chosen_model(spec, router_)) == "openai":
            model = chosen_model(spec, router_)
        elif router_.provider_of(model) != "openai":
            model = router_.tiers["strong"]
        agent, model_name = build_agent(spec, router_, self.model_provider(), model_override=model)
        try:
            result = await run_once(
                agent,
                model_name,
                router_,
                [{"role": "user", "content": question}],
                context,
                budget_left(context.settings),
            )
        except BudgetExceeded as e:
            return f"Can't look that up: {e}"
        new_usage = context.usage[spent_before:]
        call.pending_cost += sum(u.cost_usd for u in new_usage)
        call.cost_usd += sum(u.cost_usd for u in new_usage)
        with session_scope() as s:
            from junior.chat.history import save_usage

            save_usage(s, new_usage, call.conversation_id, None, mode="call")
        return result.text or "I couldn't find an answer."

    # -- end -------------------------------------------------------------------

    async def end(self, call_id: str, reason: str = "ended by you", gateway=None) -> bool:
        call = self.calls.get(call_id)
        if call is None or call.ended:
            return False
        call.ended = True
        call.end_reason = reason
        try:
            await (gateway or self.gateway_factory()).hangup(call_id)
        except Exception:
            log.warning("Hang-up of call %s failed (it may already be over)", call_id)
        return True

    def _add_cost(self, call: LiveCall, cost: float) -> None:
        """A response's cost goes on the answer it produced, else on the next answer."""
        if call.answer_in_response is None:
            call.pending_cost += cost
            return
        with session_scope() as s:
            message = s.get(Message, call.answer_in_response)
            if message is not None:
                message.cost_usd += cost
        call.answer_in_response = None

    def _save(
        self, call: LiveCall, role: str, text: str, steps: list | None = None, cost: float = 0.0
    ) -> int:
        with session_scope() as s:
            message = Message(
                conversation_id=call.conversation_id,
                role=role,
                source="user" if role == "user" else "assistant",
                content=text,
                steps=list(steps or []),
                cost_usd=cost,
            )
            s.add(message)
            convo = s.get(Conversation, call.conversation_id)
            convo.updated_at = utcnow()
            s.flush()
            return message.id

    def _finish(self, call: LiveCall) -> None:
        if getattr(call, "_finished", False):
            return
        call._finished = True  # type: ignore[attr-defined]
        call.ended = True
        seconds = time.monotonic() - call.started
        with session_scope() as s:
            convo = s.get(Conversation, call.conversation_id)
            empty = convo is not None and not convo.messages
            if empty:
                s.delete(convo)  # nothing was said: don't keep an empty chat
            elif call.pending_steps or call.pending_cost:
                # The call ended before the next answer (e.g. mid-lookup): show the
                # leftover tools and cost on his last answer, so nothing goes missing.
                last = s.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == call.conversation_id,
                        Message.role == "assistant",
                    )
                    .order_by(Message.id.desc())
                ).first()
                if last is not None:
                    last.steps = [*last.steps, *call.pending_steps]
                    last.cost_usd += call.pending_cost
            s.add(
                Usage(
                    agent="live_call",
                    model=call.model,
                    mode="call",
                    conversation_id=None if empty else call.conversation_id,
                    extra={"seconds": round(seconds, 1)},
                    cost_usd=0.0,
                )
            )
        audit(
            "agent_run",
            "live_call",
            detail={
                "event": "ended",
                "reason": call.end_reason or "call closed",
                "seconds": round(seconds, 1),
                "responses": call.responses,
            },
            cost_usd=call.cost_usd,
            conversation_id=None if empty else call.conversation_id,
        )
        self.calls.pop(call.call_id, None)


TOOL_FINISH_SECONDS = 30
FILLER_FIRST_SECONDS = 2.5
FILLER_EVERY_SECONDS = 7.0
FILLER_WAIT_SECONDS = 6.0
FILLER_NOTE = (
    "\n\n# Right now\nYou are still looking something up for them. Say ONE short, calm, "
    "natural line (3 to 8 words) so they know you're on it, describing what you're doing, "
    "for example \"Abhi dekh raha hoon, bas ek second\" or \"Still pulling that up\". "
    "Never repeat an earlier line. Don't answer yet and don't ask a question."
)

URDU_LETTERS = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u0900-\u097F]")
LANGUAGE_NOTES = {
    "urdu": (
        "\n\n# Language right now\nThey are speaking URDU now. Reply in Urdu (Urdu script in "
        "your text), with your accent, until they switch to English."
    ),
    "english": (
        "\n\n# Language right now\nThey are speaking ENGLISH now. Reply in English, with your "
        "accent, until they switch to Urdu."
    ),
}


def is_roman(text: str) -> bool:
    """Mostly Latin letters (e.g. Roman Urdu or English)."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    latin = sum(1 for ch in letters if ch.isascii())
    return latin / len(letters) > 0.6


def spoken_language(text: str) -> str:
    """Urdu if the words are mostly in Urdu (or Hindi) script, else English."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "english"
    urdu = sum(1 for ch in letters if URDU_LETTERS.match(ch))
    return "urdu" if urdu / len(letters) >= 0.3 else "english"


class CallLimitReached(Exception):
    pass


# ---- API -------------------------------------------------------------------------


class StartCall(BaseModel):
    sdp: str = Field(min_length=10, max_length=100_000)


class EndCall(BaseModel):
    call_id: str = Field(min_length=1, max_length=200)


@router.post("/api/call/start")
async def start_call(request: Request, body: StartCall) -> dict:
    manager: CallManager = request.app.state.calls
    try:
        call, answer = await manager.start(body.sdp)
    except (BudgetExceeded, CallLimitReached) as e:
        raise HTTPException(429, str(e)) from None
    except NoApiKeyError as e:
        raise HTTPException(503, str(e)) from None
    except Exception as e:
        log.exception("Starting a live call failed")
        audit("agent_run", "live_call", result="error", detail={"error": f"{type(e).__name__}: {e}"})
        raise HTTPException(502, f"Couldn't start the call: {e}") from None
    return {"sdp": answer, "call_id": call.call_id, "conversation_id": call.conversation_id}


@router.post("/api/call/end")
async def end_call(request: Request, body: EndCall) -> dict:
    manager: CallManager = request.app.state.calls
    return {"ended": await manager.end(body.call_id)}


@router.get("/api/call/limits")
def call_limits() -> dict:
    settings = all_settings()
    used = call_seconds_today(settings["timezone"]) / 60
    allowed = float(settings["call_minutes_per_day"])
    return {
        "minutes_used": round(used, 1),
        "minutes_allowed": allowed,
        "minutes_left": round(max(allowed - used, 0), 1),
        "model": get_router().audio_model("realtime"),
    }
