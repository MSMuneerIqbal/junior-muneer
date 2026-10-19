"""Live calls with Google Gemini Live (Settings → Live calls → Voice engine), next to OpenAI Realtime (calls.py).

How a Gemini call works:
  1. The browser opens  WS /ws/call/gemini  and streams your microphone: raw 16-bit PCM, 16 kHz, mono.
  2. The backend opens a Gemini Live session (google-genai, client.aio.live.connect) with GEMINI_API_KEY, so the
     browser never sees a key. Audio goes to Gemini as you speak; his voice (24 kHz PCM) comes back and is
     passed to the browser as it arrives. Gemini's own voice activity detection decides when you've finished,
     and you can interrupt him ("interrupted": the browser stops playing).
  3. Tools: Google Search (grounding) plus Junior's own: the news agents, ask_junior, save/forget memory. They
     run here, with the same safety rules as OpenAI calls (calls.CallManager.run_tool).
  4. Both sides are saved as a chat (from Gemini's transcriptions), the cost of every turn is recorded, and the
     daily call-minutes limit and the daily cap end the call. Gemini sessions last at most 15 minutes.

Messages to the browser (JSON text frames; audio is binary frames):
    {"type": "live", "conversation_id", "model"}           the session is open
    {"type": "you" | "junior", "text", "final"}            transcript lines
    {"type": "interrupted"}                                 you spoke over him: stop his audio now
    {"type": "turn_complete"}                               he finished speaking
    {"type": "checking", "label"}                           a tool is running
    {"type": "ended", "reason"} / {"type": "error", "message"}
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from junior.agent.builder import NoApiKeyError
from junior.agent.context import TurnContext
from junior.agent.helpers import HelperRunner
from junior.audit import audit
from junior.calls import (
    AI_NEWS_TOOL, ASK_JUNIOR_TOOL, FORGET_MEMORY_TOOL, PAKISTAN_NEWS_TOOL, SAVE_MEMORY_TOOL, WEB_SEARCH_TOOL,
    CallManager, LiveCall, call_seconds_today, spoken_language,
)
from junior.config import get_settings
from junior.costs import BudgetExceeded, budget_left
from junior.db import Conversation, Usage, session_scope
from junior.models import get_router
from junior.settings_store import all_settings
from junior.timeutil import zone

log = logging.getLogger(__name__)
router = APIRouter()

GEMINI_MODELS = ("gemini-3.8-live", "gemini-2.5-flash-native-audio-preview-12-2025")
SESSION_LIMIT_SECONDS = 15 * 60  # Gemini Live: audio-only sessions last up to 15 minutes
INPUT_MIME = "audio/pcm;rate=16000"

# Your words for the Gemini session, word for word.
URDISH_INSTRUCTION = (
    "You are a helpful Pakistani voice assistant. Speak naturally in Pakistani Urdu and English (Urdish) matching "
    "the user's language. Strictly use authentic Pakistani Urdu vocabulary and pronunciation (e.g., Shukriya, "
    "Meharbani, Tafseel, Masala) and never use Hindi vocabulary (e.g., Dhanyawad, Kripya, Samasya). Keep spoken "
    "responses natural, warm, and concise (1 to 2 sentences) for live calling."
)

# Junior's own tools, as Gemini function declarations. Google Search replaces our web_search when it's on.
CUSTOM_TOOLS = [AI_NEWS_TOOL, PAKISTAN_NEWS_TOOL, ASK_JUNIOR_TOOL, SAVE_MEMORY_TOOL, FORGET_MEMORY_TOOL]


def declarations(tools: list[dict]) -> list[dict]:
    return [{"name": t["name"], "description": t["description"], "parameters_json_schema": t["parameters"]} for t in tools]


def session_config(instructions: str, voice: str, google_search: bool = True) -> dict:
    """The Live session: audio out, Junior's personality plus the Urdish instruction, tools, transcripts."""
    tools: list[dict] = [{"function_declarations": declarations(CUSTOM_TOOLS + ([] if google_search else [WEB_SEARCH_TOOL]))}]
    if google_search:  # Google Search grounding and reading links; if refused, our own web_search instead
        tools[0:0] = [{"google_search": {}}, {"url_context": {}}]
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": f"{instructions}\n\n# Voice\n{URDISH_INSTRUCTION}",
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "tools": tools,
    }


def turn_cost(usage: Any, prices: dict[str, float]) -> float:
    """One turn's cost from Gemini's usage numbers (audio and text priced separately)."""

    def by_modality(details: Any) -> tuple[int, int]:
        audio = text = 0
        for d in details or []:
            modality = str(getattr(d, "modality", "") or "").upper()
            count = int(getattr(d, "token_count", 0) or 0)
            if "AUDIO" in modality:
                audio += count
            else:
                text += count
        return audio, text

    audio_in, text_in = by_modality(getattr(usage, "prompt_tokens_details", None))
    audio_out, text_out = by_modality(getattr(usage, "response_tokens_details", None))
    if not (audio_in or text_in):
        text_in = int(getattr(usage, "prompt_token_count", 0) or 0)
    if not (audio_out or text_out):
        audio_out = int(getattr(usage, "response_token_count", 0) or 0)
    return (
        audio_in * prices.get("audio_input", 0) + text_in * prices.get("text_input", 0)
        + audio_out * prices.get("audio_output", 0) + text_out * prices.get("text_output", 0)
    ) / 1_000_000


# ---- talking to Gemini (swappable for tests) --------------------------------------------


class GeminiGateway:
    """The real Gemini Live API through the official SDK."""

    def connect(self, model: str, config: dict):
        from google import genai

        key = get_settings().gemini_api_key
        if not key:
            raise RuntimeError("Gemini needs GEMINI_API_KEY in backend/.env.")
        return genai.Client(api_key=key).aio.live.connect(model=model, config=config)

    @staticmethod
    async def send_audio(session, data: bytes) -> None:
        from google.genai import types

        await session.send_realtime_input(audio=types.Blob(data=data, mime_type=INPUT_MIME))

    @staticmethod
    async def send_tool_responses(session, responses: list[dict]) -> None:
        from google.genai import types

        await session.send_tool_response(function_responses=[types.FunctionResponse(**r) for r in responses])


class FakeGemini:
    """A pretend Gemini (FAKE_AI with GEMINI_API_KEY=fake): when it hears you, it says one line. Nothing leaves the PC."""

    def connect(self, model: str, config: dict):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def session():
            yield {"queue": asyncio.Queue(), "heard": False}
        return session()

    @staticmethod
    async def send_audio(session, data: bytes) -> None:
        from types import SimpleNamespace as NS

        if session["heard"]:
            return
        session["heard"] = True

        def content(**kw):
            base = {"input_transcription": None, "output_transcription": None, "model_turn": None,
                    "interrupted": False, "turn_complete": False}
            return NS(server_content=NS(**{**base, **kw}), usage_metadata=None, tool_call=None)

        for message in (
            content(input_transcription=NS(text="Assalam o alaikum")),
            content(output_transcription=NS(text="(fake Gemini) Walaikum salam! Kya haal hai?"),
                    model_turn=NS(parts=[NS(inline_data=NS(data=b"\x00\x00" * 4800))])),  # 0.2 s of silence
            content(turn_complete=True),
        ):
            await session["queue"].put(message)

    @staticmethod
    async def send_tool_responses(session, responses: list[dict]) -> None:
        return None

    # The pretend session's receive(), bound through the dict.
    @staticmethod
    async def receive_from(session):
        while True:
            message = await session["queue"].get()
            yield message
            if message.server_content.turn_complete:
                return


GATEWAY: Any = None  # tests put a fake Gemini here


def gateway() -> Any:
    if GATEWAY is not None:
        return GATEWAY
    s = get_settings()
    if s.fake_ai and s.gemini_api_key == "fake":
        return FakeGemini()
    return GeminiGateway()


def receive(gw: Any, session: Any):
    """The session's messages for one turn (the pretend Gemini keeps its session in a dict)."""
    return gw.receive_from(session) if isinstance(gw, FakeGemini) else session.receive()


# ---- one call ------------------------------------------------------------------------------


class GeminiCall:
    def __init__(self, ws: WebSocket, manager: CallManager, model: str, settings: dict) -> None:
        self.ws, self.manager, self.model, self.settings = ws, manager, model, settings
        self.gw = gateway()
        self.call: LiveCall | None = None
        self.you, self.junior = "", ""  # this turn's transcript so far
        self.prices = get_router().audio_price(model)

    async def start(self) -> None:
        local = datetime.now(zone(self.settings["timezone"]))
        with session_scope() as s:
            convo = Conversation(title=f"Live call · {local:%d %b %H:%M}", kind="call")
            s.add(convo)
            s.flush()
            conversation_id = convo.id
        try:  # the helper agents (news, ask_junior); without an OpenAI key the call still works, those tools say so
            helpers = HelperRunner(self.manager.registry, self.manager.model_provider())
        except NoApiKeyError:
            helpers = None
        context = TurnContext(conversation_id=conversation_id, settings=self.settings, helpers=helpers)
        instructions = self.manager.call_instructions(self.settings)
        self.call = LiveCall(call_id=f"gemini-{uuid.uuid4().hex[:12]}", conversation_id=conversation_id,
                             model=self.model, context=context, instructions=instructions)
        self.manager.calls[self.call.call_id] = self.call
        audit("agent_run", "live_call", result="ok", detail={"event": "started", "model": self.model, "engine": "gemini"},
              conversation_id=conversation_id)

    async def run(self, limit_seconds: float) -> None:
        call = self.call
        voice = self.settings.get("gemini_voice") or "Charon"
        try:
            try:
                connection = self.gw.connect(self.model, session_config(call.instructions, voice, google_search=True))
                session = await connection.__aenter__()
            except Exception as e:  # e.g. this model doesn't take Google Search: use our own web_search
                log.info("Gemini Live with Google Search didn't start (%s); trying with our web search", e)
                connection = self.gw.connect(self.model, session_config(call.instructions, voice, google_search=False))
                session = await connection.__aenter__()
            try:
                await self.ws.send_json({"type": "live", "conversation_id": call.conversation_id, "model": self.model})
                upstream = asyncio.create_task(self._from_browser(session))
                downstream = asyncio.create_task(self._from_gemini(session))
                timer = asyncio.create_task(asyncio.sleep(max(min(limit_seconds, SESSION_LIMIT_SECONDS), 0)))
                done, pending = await asyncio.wait({upstream, downstream, timer}, return_when=asyncio.FIRST_COMPLETED)
                if timer in done:
                    call.end_reason = "today's call minutes ran out" if limit_seconds <= SESSION_LIMIT_SECONDS else "Gemini's 15-minute session limit"
                    await self._tell({"type": "ended", "reason": call.end_reason})
                for task in pending:
                    task.cancel()
                for task in done:
                    if task is not timer and task.exception() and not call.end_reason:
                        raise task.exception()
            finally:
                await connection.__aexit__(None, None, None)
        except Exception as e:
            log.exception("Gemini call %s stopped", call.call_id)
            call.end_reason = call.end_reason or f"connection lost: {type(e).__name__}"
            await self._tell({"type": "error", "message": f"The Gemini call stopped: {e}"})
        finally:
            await self._save_turn()
            self.manager._finish(call)

    async def _tell(self, message: dict) -> None:
        try:
            await self.ws.send_json(message)
        except Exception:  # the browser already left
            pass

    async def _from_browser(self, session) -> None:
        while True:
            message = await self.ws.receive()
            if message.get("type") == "websocket.disconnect":
                self.call.end_reason = self.call.end_reason or "ended by you"
                return
            if message.get("bytes"):
                await self.gw.send_audio(session, message["bytes"])
            elif message.get("text"):
                try:
                    command = json.loads(message["text"])
                except ValueError:
                    continue
                if command.get("type") == "end":
                    self.call.end_reason = "ended by you"
                    return

    async def _from_gemini(self, session) -> None:
        while not self.call.ended:  # receive() ends after each turn; keep listening
            got = False
            async for message in receive(self.gw, session):
                got = True
                await self._handle(session, message)
            if not got:
                await asyncio.sleep(0.05)  # nothing came: don't spin

    async def _handle(self, session, message: Any) -> None:
        call = self.call
        content = getattr(message, "server_content", None)
        if content is not None:
            if getattr(content, "interrupted", False):
                await self._tell({"type": "interrupted"})
            heard = getattr(content, "input_transcription", None)
            if heard is not None and getattr(heard, "text", None):
                self.you += heard.text
                await self._tell({"type": "you", "text": self.you, "final": False})
            said = getattr(content, "output_transcription", None)
            if said is not None and getattr(said, "text", None):
                if self.you:
                    await self._save_you()
                self.junior += said.text
                await self._tell({"type": "junior", "text": self.junior, "final": False})
            turn = getattr(content, "model_turn", None)
            for part in getattr(turn, "parts", None) or []:
                blob = getattr(part, "inline_data", None)
                if blob is not None and getattr(blob, "data", None):
                    await self.ws.send_bytes(blob.data)
            if getattr(content, "turn_complete", False):
                await self._save_turn()
                await self._tell({"type": "turn_complete"})
        usage = getattr(message, "usage_metadata", None)
        if usage is not None:
            cost = turn_cost(usage, self.prices)
            if cost:
                self._record(usage, cost)
        tool_call = getattr(message, "tool_call", None)
        if tool_call is not None:
            await self._run_tools(session, tool_call)

    async def _run_tools(self, session, tool_call: Any) -> None:
        responses = []
        for fc in getattr(tool_call, "function_calls", None) or []:
            await self._tell({"type": "checking", "label": fc.name})
            if self.you:
                await self._save_you()
            if self.call.context.helpers is None and fc.name in ("web_search", "ai_news", "pakistan_news", "ask_junior"):
                result = "That needs the OpenAI key (OPENAI_API_KEY in backend/.env), which isn't set. Say so briefly."
            else:
                result = await self.manager.run_tool(self.call, fc.name, json.dumps(dict(fc.args or {})))
            responses.append({"id": fc.id, "name": fc.name, "response": {"result": result}})
        if responses:
            await self.gw.send_tool_responses(session, responses)

    async def _save_you(self) -> None:
        call, text = self.call, self.you.strip()
        self.you = ""
        if not text:
            return
        await self._tell({"type": "you", "text": text, "final": True})
        message_id = self.manager._save(call, "user", text)
        call.context.user_message_ids.append(message_id)
        call.context.outside_content_seen = False  # a new turn of yours
        call.language = spoken_language(text)

    async def _save_turn(self) -> None:
        """Your words and his answer, saved when his turn ends (with the tools he used and their cost)."""
        if self.you:
            await self._save_you()
        call, text = self.call, self.junior.strip()
        self.junior = ""
        if not text:
            return
        await self._tell({"type": "junior", "text": text, "final": True})
        text = await self.manager._in_urdu_script(call, text)
        call.answer_in_response = self.manager._save(call, "assistant", text, steps=call.pending_steps, cost=call.pending_cost)
        call.pending_steps, call.pending_cost = [], 0.0
        call.responses += 1

    def _record(self, usage: Any, cost: float) -> None:
        call = self.call
        with session_scope() as s:
            s.add(Usage(
                agent="junior_muneer_live", model=self.model, mode="call", conversation_id=call.conversation_id,
                input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(usage, "response_token_count", 0) or 0),
                extra={"engine": "gemini"}, cost_usd=cost,
            ))
        call.cost_usd += cost
        self.manager._add_cost(call, cost)


@router.websocket("/ws/call/gemini")
async def gemini_call(ws: WebSocket) -> None:
    await ws.accept()
    manager: CallManager = ws.app.state.calls
    settings = all_settings()
    model = settings.get("voice_provider_model")
    if model not in GEMINI_MODELS:
        await ws.send_json({"type": "error", "message": "Gemini isn't the voice engine in Settings → Live calls."})
        await ws.close()
        return
    if not get_settings().gemini_api_key and GATEWAY is None:  # (the pretend Gemini needs GEMINI_API_KEY=fake)
        await ws.send_json({"type": "error", "message": "Gemini calls need GEMINI_API_KEY in backend/.env (then restart)."})
        await ws.close()
        return
    try:
        budget_left(settings)
    except BudgetExceeded as e:
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close()
        return
    limit = float(settings["call_minutes_per_day"]) * 60 - call_seconds_today(settings["timezone"])
    if limit <= 0:
        await ws.send_json({"type": "error", "message": (
            f"Today's live-call limit ({settings['call_minutes_per_day']} minutes) is used up. "
            "You can raise it in Settings, or keep chatting by text or voice messages.")})
        await ws.close()
        return
    call = GeminiCall(ws, manager, model, settings)
    await call.start()
    started = time.monotonic()
    try:
        await call.run(limit)
    except WebSocketDisconnect:
        pass
    finally:
        log.info("Gemini call ended after %.0f s", time.monotonic() - started)
        try:
            await ws.close()
        except Exception:
            pass
