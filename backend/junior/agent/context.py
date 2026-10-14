"""What an agent knows about the current turn (passed to every tool)."""

from dataclasses import dataclass, field
from typing import Any


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

    def mark_outside(self) -> None:
        self.outside_content_seen = True
