"""One chat turn: save your message, run Junior Muneer, stream the answer, save it."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from junior.agent.builder import ModelProvider, NoApiKeyError, build_agent, chosen_model
from junior.agent.context import TurnContext
from junior.agent.helpers import HelperRunner
from junior.agent.runner import TurnResult, stream_turn
from junior.approvals import attach_to_message
from junior.audit import audit
from junior.chat.history import build_input, save_usage, summarize_if_long
from junior.costs import BudgetExceeded, budget_left
from junior.db import Conversation, Message, session_scope
from junior.db.models import utcnow
from junior.models import get_router
from junior.registry import Registry
from junior.settings_store import all_settings
from junior.voice import audio_path

log = logging.getLogger(__name__)

MAIN_AGENT = "junior_muneer"
# Other providers (e.g. DeepSeek) can queue requests for minutes when busy.
FIRST_WORDS_SECONDS = 20  # no first words by then: answer with OpenAI instead
STALL_SECONDS = 60  # silence mid-answer for this long: give up
SUMMARY_SECONDS = 90
TITLE_LENGTH = 60


def title_from(text: str) -> str:
    words = " ".join(text.split())
    if len(words) <= TITLE_LENGTH:
        return words or "New chat"
    return words[:TITLE_LENGTH].rsplit(" ", 1)[0] + "…"


class ChatError(Exception):
    """A problem to show in the chat instead of an answer."""


class ChatService:
    def __init__(self, registry: Registry, model_provider: Callable[[], ModelProvider]) -> None:
        self.registry = registry
        # Called per message, so a missing API key is reported in the chat, not at startup.
        self.model_provider = model_provider

    # ---- storage ------------------------------------------------------------

    def _start(
        self,
        conversation_id: int | None,
        text: str,
        audio_id: str | None = None,
        audio_seconds: float | None = None,
    ) -> tuple[int, int, bool]:
        """Save your message (creating the chat if needed). Returns ids and 'is new'."""
        if audio_id is not None and audio_path(audio_id) is None:
            raise ChatError("That voice recording wasn't found. Please record it again.")
        with session_scope() as s:
            convo = s.get(Conversation, conversation_id) if conversation_id else None
            if conversation_id and convo is None:
                raise ChatError(f"Chat {conversation_id} doesn't exist (was it deleted?).")
            is_new = convo is None
            if convo is None:
                convo = Conversation(title=title_from(text), kind="voice" if audio_id else "text")
                s.add(convo)
            else:
                convo.updated_at = utcnow()
            message = Message(
                role="user",
                source="user",
                content=text,
                audio_file=audio_id,
                audio_seconds=audio_seconds,
            )
            convo.messages.append(message)
            s.flush()
            return convo.id, message.id, is_new

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

    def _save_partial_usage(self, conversation_id: int, context: TurnContext) -> None:
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

    async def reply(
        self,
        conversation_id: int | None,
        text: str,
        audio_id: str | None = None,
        audio_seconds: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        text = text.strip()
        if not text:
            yield {"type": "error", "message": "Empty message."}
            return
        try:
            conversation_id, user_message_id, is_new = self._start(
                conversation_id, text, audio_id, audio_seconds
            )
        except ChatError as e:
            yield {"type": "error", "message": str(e)}
            return
        if is_new:
            with session_scope() as s:
                title = s.get(Conversation, conversation_id).title
            yield {"type": "conversation", "id": conversation_id, "title": title}
        yield {"type": "user_message", "id": user_message_id, "conversation_id": conversation_id}

        settings = all_settings()
        context = TurnContext(conversation_id=conversation_id, settings=settings)
        try:
            budget = budget_left(settings)
            provider = self.model_provider()
            router = get_router()
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
            items, context.user_message_ids = build_input(conversation_id, settings["user_name"])
            result: TurnResult | None = None
            fallback_step = None
            stream = stream_turn(agent, model_name, router, items, context, budget)
            other_provider = router.provider_of(model_name) != "openai"
            first = True
            while True:
                try:
                    if other_provider:
                        # Other providers (DeepSeek) can stall for minutes when busy.
                        limit = FIRST_WORDS_SECONDS if first else STALL_SECONDS
                        event = await asyncio.wait_for(anext(stream), limit)
                    else:
                        event = await anext(stream)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    await stream.aclose()
                    if not first:
                        raise RuntimeError(
                            f"{model_name} stopped responding mid-answer. Please try again."
                        ) from None
                    # Busy: answer with the default OpenAI model instead.
                    spec = self.registry.get(MAIN_AGENT)
                    backup = router.model_for(MAIN_AGENT, spec.model)
                    if router.provider_of(backup) != "openai":
                        backup = router.tiers["strong"]
                    label = router.providers.get(router.provider_of(model_name), {}).get(
                        "label", model_name
                    )
                    log.warning("%s gave no answer in %ss; using %s", model_name, limit, backup)
                    fallback_step = {
                        "id": "fallback",
                        "kind": "tool",
                        "name": "fallback",
                        "label": f"{label} is busy right now, so {backup} answered",
                        "status": "done",
                    }
                    yield {"type": "step", **fallback_step}
                    agent, model_name = build_agent(spec, router, provider, model_override=backup)
                    stream = stream_turn(agent, model_name, router, items, context, budget)
                    other_provider = False
                    continue
                first = False
                if event["type"] == "final":
                    result = event["result"]
                else:
                    yield event
            if result is not None and fallback_step:
                result.steps.insert(0, fallback_step)
        except (NoApiKeyError, BudgetExceeded) as e:
            self._save_partial_usage(conversation_id, context)
            self._audit_run(conversation_id, context, "blocked", error=str(e))
            yield {"type": "error", "message": str(e)}
            return
        except Exception as e:  # shown in the chat; details in the log
            log.exception("Chat turn failed")
            self._save_partial_usage(conversation_id, context)
            message = f"Something went wrong: {type(e).__name__}: {e}"
            self._audit_run(conversation_id, context, "error", error=message)
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
