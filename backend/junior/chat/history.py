"""Conversation memory: what of a chat goes to the model each turn.

The newest messages go in full. When a chat gets long, the older part is
folded into a running summary by the summarizer agent (small model), so
cost stays low and Junior Muneer still remembers how the chat started.
"""

import logging

from agents.items import TResponseInputItem
from sqlalchemy import select

from junior.agent.builder import ModelProvider, build_agent
from junior.agent.context import ModelUsage, TurnContext
from junior.agent.runner import TurnResult, run_once
from junior.costs import budget_left
from junior.db import Conversation, Message, Usage, session_scope
from junior.models import get_router
from junior.registry import Registry
from junior.settings_store import all_settings

log = logging.getLogger(__name__)

# Messages always sent in full.
KEEP_RECENT = 20
# Summarize once this many messages are not yet covered by the summary.
SUMMARIZE_AFTER = 30


def save_usage(
    s, usage: list[ModelUsage], conversation_id: int | None, message_id: int | None, mode: str = "text"
) -> None:
    for u in usage:
        s.add(
            Usage(
                agent=u.agent,
                model=u.model,
                mode=mode,
                conversation_id=conversation_id,
                message_id=message_id,
                input_tokens=u.input_tokens,
                cached_input_tokens=u.cached_input_tokens,
                output_tokens=u.output_tokens,
                extra={"web_searches": u.web_searches} if u.web_searches else {},
                cost_usd=u.cost_usd,
            )
        )


def _unsummarized(s, convo: Conversation) -> list[Message]:
    return list(
        s.scalars(
            select(Message)
            .where(Message.conversation_id == convo.id, Message.id > convo.summary_upto_id)
            .order_by(Message.id)
        )
    )


def build_input(conversation_id: int, user_name: str) -> tuple[list[TResponseInputItem], list[int]]:
    """Model input for this chat (summary + recent messages), and the ids of your own messages."""
    with session_scope() as s:
        convo = s.get(Conversation, conversation_id)
        messages = _unsummarized(s, convo)
        summary = convo.summary
        user_ids = list(
            s.scalars(
                select(Message.id).where(
                    Message.conversation_id == conversation_id, Message.source == "user"
                )
            )
        )
    items: list[TResponseInputItem] = []
    if summary:
        items.append(
            {
                "role": "developer",
                "content": (
                    "Summary of the earlier part of this chat, written by a helper. "
                    f"Only the points under '{user_name} said' come from {user_name}.\n\n{summary}"
                ),
            }
        )
    for m in messages:
        if m.role == "user":
            items.append({"role": "user", "content": m.content})
        elif m.content:
            items.append({"role": "assistant", "content": m.content})
    return items, user_ids


async def summarize_if_long(
    conversation_id: int, registry: Registry, model_provider: ModelProvider
) -> TurnResult | None:
    """Fold older messages into the summary when the chat has grown long."""
    settings = all_settings()
    with session_scope() as s:
        convo = s.get(Conversation, conversation_id)
        if convo is None:
            return None
        pending = _unsummarized(s, convo)
        if len(pending) <= SUMMARIZE_AFTER:
            return None
        old = pending[:-KEEP_RECENT]
        previous = convo.summary
        upto_id = old[-1].id
        transcript = "\n\n".join(
            f"{settings['user_name'] if m.role == 'user' else 'Junior Muneer'}: {m.content}"
            for m in old
        )

    budget = budget_left(settings)  # raises BudgetExceeded when the cap is reached
    router = get_router()
    agent, model_name = build_agent(registry.get("summarizer"), router, model_provider)
    prompt = f"Summary so far:\n{previous or '(none yet)'}\n\nNext part of the chat:\n{transcript}"
    context = TurnContext(conversation_id=conversation_id, settings=settings)
    try:
        result = await run_once(
            agent, model_name, router, [{"role": "user", "content": prompt}], context, budget
        )
    except Exception:
        if context.usage:  # a failed run still cost money
            with session_scope() as s:
                save_usage(s, context.usage, conversation_id, None)
        raise
    with session_scope() as s:
        if result.text.strip():
            convo = s.get(Conversation, conversation_id)
            convo.summary = result.text.strip()
            convo.summary_upto_id = upto_id
        save_usage(s, result.usage, conversation_id, None)
    log.info("Chat %s: summarized %d older messages", conversation_id, len(old))
    return result
