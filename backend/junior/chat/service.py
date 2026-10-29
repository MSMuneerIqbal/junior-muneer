"""One chat turn: save your message, run Junior Muneer, stream the answer, save it."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from openai import APIConnectionError, InternalServerError, RateLimitError

from junior.agent.builder import ModelProvider, NoApiKeyError, build_agent, chosen_model
from junior.agent.context import TurnContext
from junior.agent.helpers import HelperRunner
from junior.agent.runner import TurnResult, stream_turn
from junior.ai_client import no_answer_message
from junior.approvals import attach_to_message
from junior.audit import audit
from junior.chat.history import build_input, save_usage, summarize_if_long
from junior.costs import BudgetExceeded, budget_left
from junior.db import Conversation, Message, Paste, session_scope
from junior.db.models import utcnow
from junior.models import get_router
from junior.registry import Registry
from junior.settings_store import all_settings
from junior.voice import audio_path

log = logging.getLogger(__name__)

MAIN_AGENT = "junior_muneer"
# Other providers (e.g. DeepSeek) can queue requests for minutes when busy.
FIRST_WORDS_SECONDS = 20  # no first words by then: answer with OpenAI instead
# Silence mid-answer (no text, no steps, no tool-call writing) for this long: give up. Generous, because a model
# can think quietly for a while over big search results (found live: DeepSeek, 42 s); each AI request also has its
# own 2-minute limit (ai_client) and the whole answer 10 minutes. A running tool never counts as silence.
STALL_SECONDS = 180
TURN_SECONDS = 600  # one answer may take at most 10 minutes (tools included); then it stops instead of hanging
SUMMARY_SECONDS = 90
TITLE_LENGTH = 60


def title_from(text: str) -> str:
    words = " ".join(text.split())
    if len(words) <= TITLE_LENGTH:
        return words or "New chat"
    return words[:TITLE_LENGTH].rsplit(" ", 1)[0] + "…"


PASTE_PLATFORMS = ("linkedin", "facebook", "instagram", "x", "upwork", "fiverr", "email", "other")
PASTE_KINDS = ("post", "comment", "job", "client_message", "order", "email", "other")
PASTE_MAX_CHARS = 20000
PASTE_LABELS = {"client_message": "client message", "job": "job post"}


def clean_paste(raw: object) -> dict[str, str] | None:
    """A pasted block from the chat, checked. Raises ChatError when it's unusable."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ChatError("Bad pasted content.")
    text = str(raw.get("text", "")).strip()
    if not text:
        raise ChatError("The Paste box is empty.")
    if len(text) > PASTE_MAX_CHARS:
        raise ChatError(f"That paste is too long ({len(text)} characters; the limit is {PASTE_MAX_CHARS}).")
    platform = raw.get("platform") if raw.get("platform") in PASTE_PLATFORMS else "other"
    kind = raw.get("kind") if raw.get("kind") in PASTE_KINDS else "other"
    url = str(raw.get("source_url") or "").strip()[:500]
    if url and not url.startswith(("https://", "http://")):
        url = ""
    return {"text": text, "platform": platform, "kind": kind, "source_url": url}


class ChatError(Exception):
    """A problem to show in the chat instead of an answer."""


class ChatService:
    def __init__(self, registry: Registry, model_provider: Callable[[], ModelProvider]) -> None:
        self.registry = registry
        # Called per message, so a missing API key is reported in the chat, not at startup.
        self.model_provider = model_provider
        self.active_chats: dict[int, int] = {}

    # ---- storage ------------------------------------------------------------

    def _start(
        self,
        conversation_id: int | None,
        text: str,
        audio_id: str | None = None,
        audio_seconds: float | None = None,
        paste: dict[str, str] | None = None,
    ) -> tuple[int, int, bool, dict | None]:
        """Save your message, and the pasted text before it (creating the chat if needed).
        Returns ids, 'is new' and the saved paste."""
        if audio_id is not None and audio_path(audio_id) is None:
            raise ChatError("That voice recording wasn't found. Please record it again.")
        with session_scope() as s:
            convo = s.get(Conversation, conversation_id) if conversation_id else None
            if conversation_id and convo is None:
                raise ChatError(f"Chat {conversation_id} doesn't exist (was it deleted?).")
            is_new = convo is None
            if convo is None:
                title = text
                if paste:
                    what = PASTE_LABELS.get(paste["kind"], paste["kind"])
                    title = f"Pasted {what}: {text}" if text else f"Pasted {what}"
                convo = Conversation(title=title_from(title), kind="voice" if audio_id else "text")
                s.add(convo)
            else:
                convo.updated_at = utcnow()
            saved_paste = None
            if paste:
                # Someone else's words: role "user" (it came from your side) but
                # source "outside", so it can never back a memory.
                pasted = Message(role="user", source="outside", content=paste["text"])
                convo.messages.append(pasted)
                s.flush()
                row = Paste(
                    platform=paste["platform"],
                    kind=paste["kind"],
                    text=paste["text"],
                    source_url=paste["source_url"],
                    conversation_id=convo.id,
                    message_id=pasted.id,
                )
                s.add(row)
                s.flush()
                saved_paste = {"id": row.id, "message_id": pasted.id, **paste}  # includes "text"
            message = Message(
                role="user",
                source="user",
                content=text,
                audio_file=audio_id,
                audio_seconds=audio_seconds,
            )
            convo.messages.append(message)
            s.flush()
            return convo.id, message.id, is_new, saved_paste

    def _finish(self, conversation_id: int, result: TurnResult) -> int:
        with session_scope() as s:
            message = Message(
                conversation_id=conversation_id,
                role="assistant",
                source="assistant",
                content=result.text,
                steps=result.steps,
                cost_usd=result.cost_usd,
            )
            s.add(message)
            s.flush()
            save_usage(s, result.usage, conversation_id, message.id)
            s.get(Conversation, conversation_id).updated_at = utcnow()
            return message.id

    def _save_partial_usage(self, conversation_id: int | None, context: TurnContext) -> None:
        """A failed or stopped turn still cost money: record it."""
        if context.usage:
            with session_scope() as s:
                save_usage(s, context.usage, conversation_id, None)

    def _audit_run(
        self, conversation_id: int, context: TurnContext, result: str, **detail: object
    ) -> None:
        audit(
            "agent_run",
            MAIN_AGENT,
            result=result,
            detail={
                "models": sorted({u.model for u in context.usage}),
                "model_calls": len(context.usage),
                **detail,
            },
            cost_usd=sum(u.cost_usd for u in context.usage),
            conversation_id=conversation_id,
        )

    # ---- the turn -------------------------------------------------------------

    async def reply(self, conversation_id, text, audio_id=None, audio_seconds=None, paste=None):
        from junior.chat.reset import COMMANDS, reset_session
        if text.strip().casefold() in COMMANDS and paste is None:
            if conversation_id in self.active_chats:
                yield {"type": "error", "message": "A reply is still running in this chat. Send /clear when it finishes."}
                return
            new = reset_session(conversation_id)
            yield {"type": "session_reset", "previous_id": conversation_id, "conversation_id": new["id"]}
            yield {"type": "conversation", **new}
            result = TurnResult(text="Fresh session started. Previous chat history and summary were cleared. Saved files, notes and profile memory are still available.", usage=[], steps=[])
            mid = self._finish(new["id"], result)
            yield {"type": "done", "conversation_id": new["id"], "message_id": mid, "text": result.text, "steps": [], "cost_usd": 0.}
            return
        active_id = conversation_id
        registered = False
        try:
            async for event in self._reply(conversation_id, text, audio_id, audio_seconds, paste):
                if event["type"] == "user_message":
                    active_id = event["conversation_id"]
                    self.active_chats[active_id] = self.active_chats.get(active_id, 0) + 1
                    registered = True
                yield event
        finally:
            if registered:
                self.active_chats[active_id] -= 1
                if not self.active_chats[active_id]:
                    self.active_chats.pop(active_id)

    async def _reply(
        self,
        conversation_id: int | None,
        text: str,
        audio_id: str | None = None,
        audio_seconds: float | None = None,
        paste: object = None,
    ) -> AsyncIterator[dict[str, Any]]:
        text = text.strip()
        try:
            cleaned = clean_paste(paste)
            if not text and cleaned:
                text = "I pasted this. What do you think, and how should I respond?"
            if not text:
                yield {"type": "error", "message": "Empty message."}
                return
            conversation_id, user_message_id, is_new, saved_paste = self._start(
                conversation_id, text, audio_id, audio_seconds, cleaned
            )
        except ChatError as e:
            yield {"type": "error", "message": str(e)}
            return
        if is_new:
            with session_scope() as s:
                title = s.get(Conversation, conversation_id).title
            yield {"type": "conversation", "id": conversation_id, "title": title}
        if saved_paste:
            yield {
                "type": "paste",
                "message_id": saved_paste["message_id"],
                "platform": saved_paste["platform"],
                "kind": saved_paste["kind"],
                "source_url": saved_paste["source_url"],
            }
        yield {"type": "user_message", "id": user_message_id, "conversation_id": conversation_id, "text": text}

        settings = all_settings()
        from junior.permissions import ACTION_CHANNEL, get_mode
        if ACTION_CHANNEL.get() == "whatsapp":
            settings["permission_mode"] = get_mode()
        context = TurnContext(
            conversation_id=conversation_id, settings=settings, paste=saved_paste, user_text=text
        )
        from junior.chat.commands import handle as local_command
        context.user_message_ids = [user_message_id]
        from junior.browser.media import (active_player, continuation as music_continuation, is_request as is_music_request,
                                          is_stop_request as is_music_stop, is_change_request as is_music_change,
                                          prepare as prepare_music, prepare_stop, prepare_change)
        resumed_music = music_continuation(context, text) if saved_paste is None else None
        stop_music = bool(saved_paste is None and is_music_stop(text) and not is_music_request(text) and active_player())
        change_music = bool(saved_paste is None and is_music_change(text) and active_player())
        if saved_paste is None and (is_music_request(text) or resumed_music or stop_music or change_music):
            label = "Stopping the YouTube player" if stop_music else "Changing the song" if change_music else "Finding and playing the song"
            yield {"type": "step", "id": "music-play", "kind": "tool", "label": label, "status": "running"}
            if resumed_music and resumed_music.get("reply"):
                result_text = resumed_music["reply"]
            else:
                if resumed_music:
                    context.user_message_ids = [resumed_music["id"]]
                result_text = await prepare_stop(context, text) if stop_music else await prepare_change(context, text) if change_music else await prepare_music(context, resumed_music["text"] if resumed_music else text)
            yield {"type": "step", "id": "music-play", "kind": "tool", "label": label, "status": "done"}
            for event in context.pending_events:
                yield event
            if result_text.startswith("Done (their rule is Auto): "):
                result_text = result_text.removeprefix("Done (their rule is Auto): ").removesuffix(" Tell them in one line.")
            elif result_text.startswith("NOT done yet - waiting for their OK"):
                result_text = ("The stop action is ready on the approval card. Approve it once to close Junior's player."
                               if stop_music else "The next song is ready on the approval card. Approve it once to change the song."
                               if change_music else "The song is ready on the approval card. Approve it once and Junior will start the player.")
            elif result_text.startswith("It didn't work: "):
                result_text = result_text.removesuffix(" Tell them in one line.")
            result = TurnResult(text=result_text, usage=[], steps=[])
            message_id = self._finish(conversation_id, result)
            attach_to_message(context.approval_ids, message_id)
            yield {"type": "done", "conversation_id": conversation_id, "message_id": message_id,
                   "text": result_text, "steps": [], "cost_usd": 0.0}
            return
        # Git fetch can take up to 30 seconds; keep the event loop responsive to Pause/Stop.
        if local_result := await asyncio.to_thread(local_command, context, text, saved_paste):
            for event in context.pending_events:
                yield event
            message_id = self._finish(conversation_id, local_result)
            attach_to_message(context.approval_ids, message_id)
            yield {"type": "done", "conversation_id": conversation_id, "message_id": message_id,
                   "text": local_result.text, "steps": [], "cost_usd": 0.0}
            return
        context.start_background = lambda title, request: self.start_background(
            conversation_id, title, request, saved_paste, context
        )
        context.start_documents = lambda request, fmt, slides: self.start_background(
            conversation_id, request[:100], request, saved_paste, context,
            worker="documents_agent", output_format=fmt, slide_count=slides
        )
        context.start_notes = lambda options: self.start_background(
            conversation_id, options["title"] or "Class notes", context.user_text, saved_paste, context,
            worker="notes_agent", output_format="class_notes", notes_options=options
        )
        try:
            budget = budget_left(settings)
            from junior.documents.limits import task_provider
            router = get_router()
            provider = task_provider(self.model_provider(), context, router)
            spec = self.registry.get(MAIN_AGENT)
            # Other providers (DeepSeek) are for typed chat only: a voice message is
            # answered by the default OpenAI model, so voice never waits on them.
            voice_override = None
            if audio_id is not None:
                default = router.model_for(MAIN_AGENT, spec.model)
                voice_override = (
                    default if router.provider_of(default) == "openai" else router.tiers["strong"]
                )
                if router.provider_of(chosen_model(spec, router)) == "openai":
                    voice_override = None  # your OpenAI choice is fine for voice too
            agent, model_name = build_agent(spec, router, provider, model_override=voice_override)
            context.helpers = HelperRunner(self.registry, provider)
            items, context.user_message_ids, pasted = build_input(conversation_id, settings["user_name"])
            if pasted:
                # Pasted text is in this chat: memory changes are blocked and anything
                # drafted from it waits for your OK (ground rules 3, 5 and 6).
                context.mark_outside()
            result: TurnResult | None = None
            fallback_step = None
            stream = stream_turn(agent, model_name, router, items, context, budget)
            other_provider = router.provider_of(model_name) != "openai"
            first = True
            tools_running: set[str] = set()  # a tool at work (a web search, a helper agent) isn't the model being silent
            deadline = time.monotonic() + TURN_SECONDS
            while True:
                try:
                    left = max(deadline - time.monotonic(), 0.001)
                    if other_provider:
                        # Other providers (DeepSeek) can stall for minutes when busy.
                        limit = FIRST_WORDS_SECONDS if first else STALL_SECONDS
                        if tools_running:
                            limit = left
                        event = await asyncio.wait_for(anext(stream), min(limit, left))
                    else:
                        event = await asyncio.wait_for(anext(stream), left)
                except StopAsyncIteration:
                    break
                except Exception as e:
                    if isinstance(e, TimeoutError) and time.monotonic() >= deadline:
                        await stream.aclose()
                        raise RuntimeError(
                            f"This answer took over {TURN_SECONDS // 60} minutes, so I stopped it. "
                            "Please try again, or ask for it as a background task."
                        ) from None
                    # Another provider (DeepSeek, Gemini) silent, rate-limited (free tiers) or down before any
                    # words: OpenAI answers instead. Anything else, or OpenAI itself failing, goes up as before.
                    limited = isinstance(e, (RateLimitError, InternalServerError, APIConnectionError))
                    if not (isinstance(e, TimeoutError) or (other_provider and limited)):
                        raise
                    await stream.aclose()
                    if not first:
                        if limited:
                            raise
                        raise RuntimeError(
                            f"{model_name} stopped responding mid-answer. Please try again."
                        ) from None
                    why = "hit its rate limit" if isinstance(e, RateLimitError) else "is busy right now"
                    # Busy: answer with the default OpenAI model instead.
                    spec = self.registry.get(MAIN_AGENT)
                    backup = router.model_for(MAIN_AGENT, spec.model)
                    if router.provider_of(backup) != "openai":
                        backup = router.tiers["strong"]
                    label = router.providers.get(router.provider_of(model_name), {}).get(
                        "label", model_name
                    )
                    log.warning("%s didn't answer (%s); using %s", model_name, type(e).__name__, backup)
                    fallback_step = {
                        "id": "fallback",
                        "kind": "tool",
                        "name": "fallback",
                        "label": f"{label} {why}, so {backup} answered",
                        "status": "done",
                    }
                    yield {"type": "step", **fallback_step}
                    agent, model_name = build_agent(spec, router, provider, model_override=backup)
                    stream = stream_turn(agent, model_name, router, items, context, budget)
                    other_provider = False
                    continue
                first = False
                if event["type"] == "step" and event.get("kind") in ("tool", "web_search") and event.get("id"):
                    if event.get("status") == "running":
                        tools_running.add(event["id"])
                    else:
                        tools_running.discard(event["id"])
                if event["type"] == "final":
                    result = event["result"]
                elif event["type"] != "alive":  # "still writing": only for the silence check above
                    yield event
            if result is not None and fallback_step:
                result.steps.insert(0, fallback_step)
        except (NoApiKeyError, BudgetExceeded) as e:
            self._save_partial_usage(conversation_id, context)
            self._audit_run(conversation_id, context, "blocked", error=str(e))
            self._drop_queued(context)
            yield {"type": "error", "message": str(e)}
            return
        except APIConnectionError as e:  # no answer in time, or no internet
            log.warning("Chat turn: %s: %s", type(e).__name__, e)
            self._save_partial_usage(conversation_id, context)
            message = no_answer_message(e)
            self._audit_run(conversation_id, context, "error", error=message)
            self._drop_queued(context)
            yield {"type": "error", "message": message}
            return
        except Exception as e:  # shown in the chat; details in the log
            log.exception("Chat turn failed")
            self._save_partial_usage(conversation_id, context)
            message = f"Something went wrong: {type(e).__name__}: {e}"
            self._audit_run(conversation_id, context, "error", error=message)
            self._drop_queued(context)
            yield {"type": "error", "message": message}
            return

        assert result is not None
        message_id = self._finish(conversation_id, result)
        attach_to_message(context.approval_ids, message_id)
        self._audit_run(conversation_id, context, "ok", steps=[st["label"] for st in result.steps])
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "text": result.text,
            "steps": result.steps,
            "cost_usd": result.cost_usd,
        }
        for start in context.after_turn:  # background tasks start once "I'm on it" is saved
            start()

        # After the answer is out, so it never slows the reply down. Time-limited, so a
        # stalled provider can't hold up your next message.
        try:
            await asyncio.wait_for(
                summarize_if_long(conversation_id, self.registry, provider), SUMMARY_SECONDS
            )
        except TimeoutError:
            log.warning("Chat %s: summary took too long; will try again next turn", conversation_id)
        except BudgetExceeded:
            log.info("Chat %s: summary skipped, daily cap reached", conversation_id)
        except Exception:
            log.exception("Summarizing chat %s failed; will retry next turn", conversation_id)

    # ---- background tasks (P7-02) ---------------------------------------------

    def start_background(
        self, conversation_id: int, title: str, request: str, paste: dict | None = None, context: TurnContext | None = None,
        *, worker: str = MAIN_AGENT, output_format: str = "text", slide_count: int = 10, notes_options: dict | None = None
    ) -> str:
        """Start a long request in the background (after this turn's answer); its result is posted to this chat."""
        from junior.background import MAX_RUNNING, new_task, running_count
        from junior.pause import is_paused

        if is_paused():
            return "NOT started: everything is paused. Do it now in this answer instead."
        from junior.permissions import plan_mode_refusal
        if refusal := plan_mode_refusal():
            return refusal
        if running_count() >= MAX_RUNNING:
            return f"NOT started: {MAX_RUNNING} tasks are already running in the background. Do it now instead, or ask them to wait."
        task_id = new_task(conversation_id, title, request, worker=worker, output_format=output_format)
        origin_ids = list(context.user_message_ids) if context else []

        def launch() -> None:
            work = (self._documents_background(task_id, conversation_id, title, request, paste, output_format, slide_count, origin_ids,
                                               context.user_text if context else request, notes_options)
                    if worker in ("documents_agent", "notes_agent") else self._background(task_id, conversation_id, title, request, paste))
            job = asyncio.create_task(work)
            _BACKGROUND.add(job)
            job.add_done_callback(_BACKGROUND.discard)

        if context is None:
            launch()
        else:
            context.after_turn.append(launch)
            context.queued_tasks.append(task_id)
        return (
            f"Started in the background as task {task_id}: “{title}”. Tell them you're on it, that they can keep "
            "chatting, and that the result will appear in this chat. Don't do the task yourself now."
        )

    def _drop_queued(self, context: TurnContext) -> None:
        """The turn failed: background tasks it queued never start."""
        from junior.background import finish_task

        for task_id in context.queued_tasks:
            finish_task(task_id, "failed", error="The chat answer failed before it could start. Ask again.")
        context.after_turn.clear()

    async def _background(
        self, task_id: int, conversation_id: int, title: str, request: str, paste: dict | None
    ) -> None:
        from junior.background import finish_task
        from junior.whatsapp import post_to_whatsapp

        settings = all_settings()
        context = TurnContext(conversation_id=conversation_id, settings=settings, paste=paste, user_text=request)
        context.background = True
        try:
            self._configure_task(context, task_id)
            from junior.documents.limits import task_provider
            budget = min(budget_left(settings), context.task_budget_usd)
            provider = task_provider(self.model_provider(), context)
            router = get_router()
            agent, model_name = build_agent(self.registry.get(MAIN_AGENT), router, provider)
            context.helpers = HelperRunner(self.registry, provider)
            items, context.user_message_ids, pasted = build_input(conversation_id, settings["user_name"])
            if pasted or paste:
                context.mark_outside()
            items.append(
                {
                    "role": "user",
                    "content": f"[Background task {task_id}] Do this now, fully: {request}\n"
                    "You're working in the background: I'm not waiting on this message. Reply with the finished result.",
                }
            )
            result: TurnResult | None = None
            try:
                result = await self._guarded_work(context, self._background_stream(agent, model_name, router, items, context, budget))
            except (RateLimitError, InternalServerError, APIConnectionError) as e:
                # Gemini or DeepSeek busy (e.g. "503 high demand"): OpenAI does the task instead, like in chat.
                # Only when nothing was done yet (no cards, emails or changes), so nothing happens twice.
                untouched = not (context.actions_done or context.approval_ids or context.computer_actions)
                if router.provider_of(model_name) == "openai" or not untouched or context.task_retries_used >= context.task_max_retries:
                    raise
                context.task_retries_used += 1
                spec = self.registry.get(MAIN_AGENT)
                backup = router.model_for(MAIN_AGENT, spec.model)
                if router.provider_of(backup) != "openai":
                    backup = router.tiers["strong"]
                log.warning("Background task %s: %s didn't answer (%s); using %s", task_id, model_name, type(e).__name__, backup)
                agent, model_name = build_agent(spec, router, provider, model_override=backup)
                result = None
                result = await self._guarded_work(context, self._background_stream(agent, model_name, router, items, context, budget))
            assert result is not None
            result.text = f"**Done in the background: {title}**\n\n{result.text}"
            message_id = self._finish(conversation_id, result)
            attach_to_message(context.approval_ids, message_id)
            self._audit_run(conversation_id, context, "ok", background_task=task_id)
            finish_task(task_id, "done", message_id, cost_usd=result.cost_usd)
            await post_to_whatsapp(conversation_id, result.text)  # started from WhatsApp: the result goes there too
        except Exception as e:  # posted to the chat; details in the log
            if isinstance(e, APIConnectionError):
                why = no_answer_message(e)
            elif isinstance(e, (RateLimitError, InternalServerError)):
                log.warning("Background task %s: the AI is busy: %s", task_id, e)
                why = ("The AI service was busy (too many requests right now), and part of the task was already done, "
                       "so I didn't start it again. Ask me again in a minute." if context.actions_done or context.approval_ids
                       else "The AI service was busy (too many requests right now). Ask me again in a minute.")
            elif isinstance(e, (NoApiKeyError, BudgetExceeded)):
                why = str(e)
            else:
                log.exception("Background task %s failed", task_id)
                why = f"{type(e).__name__}: {e}"
            with session_scope() as s:
                deleted = s.get(Conversation, conversation_id) is None
            self._save_partial_usage(None if deleted else conversation_id, context)
            self._audit_run(None if deleted else conversation_id, context, "error", error=why, background_task=task_id)
            if deleted:
                finish_task(task_id, "failed", error="The originating chat was deleted.", cost_usd=sum(u.cost_usd for u in context.usage))
                return
            failed = TurnResult(text=f"**I couldn't finish “{title}” in the background.** {why}", usage=[])
            message_id = self._finish(conversation_id, failed)
            from junior.db import BackgroundTask
            with session_scope() as s:
                cancelled = s.get(BackgroundTask, task_id).status == "cancelled"
            finish_task(task_id, "cancelled" if cancelled else "failed", message_id, error=why, cost_usd=sum(u.cost_usd for u in context.usage))
            await post_to_whatsapp(conversation_id, failed.text)

    def _configure_task(self, context: TurnContext, task_id: int) -> None:
        from junior.background import progress
        from junior.db import BackgroundTask
        with session_scope() as s:
            task = s.get(BackgroundTask, task_id)
            context.task_id, context.background = task_id, True
            context.task_budget_usd = task.cost_limit_usd
            context.task_deadline = time.monotonic() + task.time_limit_seconds
            context.task_max_retries = task.max_retries
        progress(task_id, "Starting", 0, context)

    async def _guarded_work(self, context, work):
        """Pause, cancel and time limits also interrupt a provider/tool that is not emitting events."""
        job = asyncio.create_task(work)
        try:
            while True:
                done, _ = await asyncio.wait({job}, timeout=.5)
                if job in done:
                    return job.result()
                context.check_task_limits()
        finally:
            if not job.done():
                job.cancel()
                import contextlib
                with contextlib.suppress(asyncio.CancelledError):
                    await job

    async def _background_stream(self, agent, model_name, router, items, context, budget):
        from junior.background import progress
        result = None
        async for event in stream_turn(agent, model_name, router, items, context, budget):
            if event["type"] == "step":
                progress(context.task_id, event.get("label", "Working"), 1, context)
            elif event["type"] == "final":
                result = event["result"]
        context.check_task_limits()
        progress(context.task_id, "Returning the result", 3, context)
        assert result is not None
        return result

    async def _documents_background(self, task_id, conversation_id, title, request, paste, output_format, slide_count, origin_ids, origin_text,
                                    notes_options=None):
        from junior.background import finish_task, progress
        from junior.db import BackgroundTask
        from junior.documents.limits import task_provider
        from junior.documents.worker import run_documents
        from junior.whatsapp import post_to_whatsapp
        context = TurnContext(conversation_id=conversation_id, settings=all_settings(), paste=paste, user_text=origin_text)
        context.user_message_ids = origin_ids
        try:
            self._configure_task(context, task_id)
            context.check_task_limits()
            provider = task_provider(self.model_provider(), context)
            context.helpers = HelperRunner(self.registry, provider)
            if notes_options is not None:
                from junior.notes.worker import run_notes
                work = run_notes(context, request, notes_options)
            else:
                work = run_documents(context, request, output_format, slide_count)
            text = await self._guarded_work(context, work)
            result = TurnResult(text=f"**Done in the background: {title}**\n\n{text}", usage=context.usage,
                                steps=[e for e in context.pending_events if e.get("type") == "step"])
            context.check_task_limits()
            message_id = self._finish(conversation_id, result)
            attach_to_message(context.approval_ids, message_id)
            progress(task_id, "Finished", 5, context)
            finish_task(task_id, "done", message_id, cost_usd=result.cost_usd)
            self._audit_run(conversation_id, context, "ok", background_task=task_id,
                            worker="notes_agent" if notes_options is not None else "documents_agent")
            await post_to_whatsapp(conversation_id, result.text, file_ids=context.generated_file_ids, approval_ids=context.approval_ids)
        except Exception as e:
            why = no_answer_message(e) if isinstance(e, APIConnectionError) else str(e)
            log.exception("Document task %s stopped", task_id)
            with session_scope() as s:
                deleted = s.get(Conversation, conversation_id) is None
            self._save_partial_usage(None if deleted else conversation_id, context)
            self._audit_run(None if deleted else conversation_id, context, "error", background_task=task_id, error=why)
            if deleted:
                finish_task(task_id, "failed", error="The originating chat was deleted.", cost_usd=sum(u.cost_usd for u in context.usage))
                return
            text = f"**I couldn't finish “{title}”.** {why[:1200]}"
            if context.generated_file_ids:
                text += "\n\nFiles already prepared: " + " ".join(f"[Download](/api/files/{i}/download)" for i in context.generated_file_ids)
            message_id = self._finish(conversation_id, TurnResult(text=text))
            attach_to_message(context.approval_ids, message_id)
            with session_scope() as s:
                task = s.get(BackgroundTask, task_id)
                cancelled = task is not None and task.status == "cancelled"
            progress(task_id, "Stopped", 0, context)
            finish_task(task_id, "cancelled" if cancelled else "failed", message_id, why, sum(u.cost_usd for u in context.usage))
            await post_to_whatsapp(conversation_id, text)


# Running background jobs (kept so they aren't garbage-collected mid-way).
_BACKGROUND: set[asyncio.Task] = set()
