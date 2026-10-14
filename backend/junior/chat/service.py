"""One chat turn: save your message, run Junior Muneer, stream the answer, save it."""

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from junior.agent.builder import ModelProvider, NoApiKeyError, build_agent
from junior.agent.context import TurnContext
from junior.agent.runner import TurnResult, stream_turn
from junior.chat.history import build_input, save_usage, summarize_if_long
from junior.db import Conversation, Message, session_scope
from junior.db.models import utcnow
from junior.models import get_router
from junior.registry import Registry
from junior.settings_store import all_settings

log = logging.getLogger(__name__)

MAIN_AGENT = "junior_muneer"
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

    def _start(self, conversation_id: int | None, text: str) -> tuple[int, int, bool]:
        """Save your message (creating the chat if needed). Returns ids and 'is new'."""
        with session_scope() as s:
            convo = s.get(Conversation, conversation_id) if conversation_id else None
            if conversation_id and convo is None:
                raise ChatError(f"Chat {conversation_id} doesn't exist (was it deleted?).")
            is_new = convo is None
            if convo is None:
                convo = Conversation(title=title_from(text))
                s.add(convo)
            else:
                convo.updated_at = utcnow()
            message = Message(role="user", source="user", content=text)
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

    # ---- the turn -------------------------------------------------------------

    async def reply(self, conversation_id: int | None, text: str) -> AsyncIterator[dict[str, Any]]:
        text = text.strip()
        if not text:
            yield {"type": "error", "message": "Empty message."}
            return
        try:
            conversation_id, user_message_id, is_new = self._start(conversation_id, text)
        except ChatError as e:
            yield {"type": "error", "message": str(e)}
            return
        if is_new:
            with session_scope() as s:
                title = s.get(Conversation, conversation_id).title
            yield {"type": "conversation", "id": conversation_id, "title": title}
        yield {"type": "user_message", "id": user_message_id, "conversation_id": conversation_id}

        try:
            provider = self.model_provider()
            router = get_router()
            settings = all_settings()
            agent, model_name = build_agent(self.registry.get(MAIN_AGENT), router, provider)
            items, user_ids = build_input(conversation_id, settings["user_name"])
            context = TurnContext(
                conversation_id=conversation_id, settings=settings, user_message_ids=user_ids
            )
            result: TurnResult | None = None
            async for event in stream_turn(agent, model_name, router, items, context):
                if event["type"] == "final":
                    result = event["result"]
                else:
                    yield event
        except NoApiKeyError as e:
            yield {"type": "error", "message": str(e)}
            return
        except Exception as e:  # shown in the chat; details in the log
            log.exception("Chat turn failed")
            yield {"type": "error", "message": f"Something went wrong: {type(e).__name__}: {e}"}
            return

        assert result is not None
        message_id = self._finish(conversation_id, result)
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "text": result.text,
            "steps": result.steps,
            "cost_usd": result.cost_usd,
        }

        # After the answer is out, so it never slows the reply down.
        try:
            await summarize_if_long(conversation_id, self.registry, provider)
        except Exception:
            log.exception("Summarizing chat %s failed; will retry next turn", conversation_id)
