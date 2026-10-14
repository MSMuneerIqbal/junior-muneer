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
from junior.settings_store import all_settings
from junior.timeutil import start_of_today_utc, zone
from junior.voice import TRANSCRIBE_PROMPT

log = logging.getLogger(__name__)
router = APIRouter()

CALL_ADDENDUM = """
## You are on a live voice call
- {{user_name}} is talking to you live; your words are spoken aloud. Keep answers short and natural, like a phone call: one to three sentences unless asked for more. No lists, tables, links or markdown.
- They can interrupt you at any time; if they do, stop and listen.
- For anything current (news, weather, prices) or anything that needs your full tools, call `ask_junior` with a clear question, say a short "let me check" first, then tell them the answer in your own words.
- `save_memory` only for facts {{user_name}} says in this call, quoting their exact words. If saving is refused, say why in one line.
- Approvals never happen by voice: anything that needs an OK shows on their screen.
"""

ASK_JUNIOR_TOOL = {
    "type": "function",
    "name": "ask_junior",
    "description": (
        "Ask the full Junior Muneer (with web search and the database) a question, "
        "e.g. today's news, the weather, prices, or something from past chats. "
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


class CallManager:
    """Keeps track of live calls and runs the backend side of each."""

    def __init__(self, gateway_factory, registry, model_provider) -> None:
        self.gateway_factory = gateway_factory
        self.registry = registry
        self.model_provider = model_provider
        self.calls: dict[str, LiveCall] = {}

    # -- start -----------------------------------------------------------------

    def session_config(self, settings: dict, model: str) -> dict:
        spec = self.registry.get("junior_muneer")
        instructions = render_instructions(spec, settings) + CALL_ADDENDUM.replace(
            "{{user_name}}", settings["user_name"]
        )
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
                    "turn_detection": {
                        "type": "semantic_vad",
                        "eagerness": "auto",
                        "interrupt_response": True,
                        "create_response": True,
                    },
                    "noise_reduction": {"type": "near_field"},
                },
                "output": {"voice": settings["tts_voice"], "speed": float(settings["tts_speed"])},
            },
            "tools": [ASK_JUNIOR_TOOL, SAVE_MEMORY_TOOL, FORGET_MEMORY_TOOL],
            "tool_choice": "auto",
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
        model = get_router().audio_model("realtime")
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
        call = LiveCall(call_id=call_id, conversation_id=conversation_id, model=model, context=context)
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
                async for event in conn:
                    await self.handle(call, conn, gateway, event)
                    if call.ended:
                        break
        except Exception as e:
            if not call.ended:
                log.exception("Live call %s stopped", call.call_id)
                call.end_reason = call.end_reason or f"connection lost: {type(e).__name__}"
        finally:
            watchdog.cancel()
            self._finish(call)

    async def _watchdog(self, call: LiveCall, gateway: RealtimeGateway, seconds_left: float):
        """Ends the call when today's call minutes run out."""
        await asyncio.sleep(max(seconds_left, 0))
        await self.end(call.call_id, "daily call-minutes limit reached", gateway)

    async def handle(self, call: LiveCall, conn, gateway: RealtimeGateway, event: Any) -> None:
        kind = _get(event, "type", default="")
        if kind == "conversation.item.input_audio_transcription.completed":
            text = (_get(event, "transcript", default="") or "").strip()
            if text:
                message_id = self._save(call, "user", text)
                call.context.user_message_ids.append(message_id)
                call.context.outside_content_seen = False  # a new turn of yours
        elif kind == "response.output_audio_transcript.done":
            text = (_get(event, "transcript", default="") or "").strip()
            if text:
                self._save(call, "assistant", text)
        elif kind == "response.function_call_arguments.done":
            output = await self.run_tool(call, _get(event, "name"), _get(event, "arguments", default="{}"))
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
            await conn.send({"type": "response.create"})
        elif kind == "response.done":
            usage = _get(event, "response", "usage")
            if usage is not None:
                cost = call_cost(usage, get_router().audio_price(call.model))
                call.responses += 1
                call.cost_usd += cost
                with session_scope() as s:
                    s.add(
                        Usage(
                            agent="junior_muneer_live",
                            model=call.model,
                            mode="call",
                            conversation_id=call.conversation_id,
                            input_tokens=_get(usage, "input_tokens", default=0),
                            cached_input_tokens=_get(
                                usage, "input_token_details", "cached_tokens", default=0
                            ),
                            output_tokens=_get(usage, "output_tokens", default=0),
                            cost_usd=cost,
                        )
                    )
                try:
                    budget_left(call.context.settings)
                except BudgetExceeded:
                    await self.end(call.call_id, "daily cost cap reached", gateway)
        elif kind == "error":
            log.warning("Realtime error on call %s: %s", call.call_id, _get(event, "error"))

    async def run_tool(self, call: LiveCall, name: str | None, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except ValueError:
            return "Invalid arguments."
        context = call.context
        if name == "save_memory":
            result = save_memory_for(context, str(args.get("fact", "")), str(args.get("your_words", "")))
        elif name == "forget_memory":
            result = forget_memory_for(context, int(args.get("memory_id", 0)))
        elif name == "ask_junior":
            result = await self._ask_junior(call, str(args.get("question", "")))
        else:
            result = f"Unknown tool {name!r}."
        context.pending_events.clear()
        audit(
            "tool_call",
            name or "?",
            result="refused" if result.startswith("NOT ") else "ok",
            detail={"agent": "junior_muneer_live", "arguments": arguments, "result": result},
            conversation_id=call.conversation_id,
        )
        return result

    async def _ask_junior(self, call: LiveCall, question: str) -> str:
        """The full Junior Muneer (web search, database) answers a question for the call."""
        from junior.agent.builder import build_agent
        from junior.agent.runner import run_once

        if not question.strip():
            return "No question given."
        context = call.context
        spent_before = len(context.usage)
        router_ = get_router()
        agent, model_name = build_agent(
            self.registry.get("junior_muneer"), router_, self.model_provider()
        )
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
        with session_scope() as s:
            from junior.chat.history import save_usage

            save_usage(s, new_usage, call.conversation_id, None, mode="call")
        # Whatever came back may include web results: treat it as outside text.
        context.mark_outside()
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

    def _save(self, call: LiveCall, role: str, text: str) -> int:
        with session_scope() as s:
            message = Message(
                conversation_id=call.conversation_id,
                role=role,
                source="user" if role == "user" else "assistant",
                content=text,
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
            s.add(
                Usage(
                    agent="live_call",
                    model=call.model,
                    mode="call",
                    conversation_id=call.conversation_id,
                    extra={"seconds": round(seconds, 1)},
                    cost_usd=0.0,
                )
            )
            convo = s.get(Conversation, call.conversation_id)
            if convo is not None and not convo.messages:
                s.delete(convo)  # nothing was said: don't keep an empty chat
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
            conversation_id=call.conversation_id,
        )
        self.calls.pop(call.call_id, None)


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
