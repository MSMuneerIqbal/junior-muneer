"""What an agent knows about the current turn (passed to every tool)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelUsage:
    """One call to the model, with its tokens and cost."""

    agent: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    web_searches: int
    cost_usd: float


@dataclass
class TurnContext:
    conversation_id: int | None
    settings: dict[str, Any]
    # IDs of your own messages (source = "user") in this conversation.
    # A memory may only be backed by one of these (ground rule 6).
    user_message_ids: list[int] = field(default_factory=list)
    # Set as soon as outside text (web results, past answers, pasted text...)
    # enters this turn. While set, memory saving is refused.
    outside_content_seen: bool = False
    # Events from tools (e.g. "memory updated") for the chat to show.
    pending_events: list[dict[str, Any]] = field(default_factory=list)
    # The paste behind this turn, if any: drafts made from it link back to it.
    paste: dict[str, Any] | None = None
    # Approval items made in this turn; shown as cards under the answer.
    approval_ids: list[int] = field(default_factory=list)
    # Every model call so far, kept here so the cost is saved even if the turn fails.
    usage: list[ModelUsage] = field(default_factory=list)
    # Runs helper agents for tools (a junior.agent.helpers.HelperRunner).
    helpers: Any = None

    def mark_outside(self) -> None:
        self.outside_content_seen = True
