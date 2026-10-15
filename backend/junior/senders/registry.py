"""Which senders are connected (P3-01). Real ones are added in P3-02 to P3-05."""

from junior.senders.base import Sender

# Which action a ready draft becomes when its platform is connected.
ACTION_FOR = {
    ("linkedin", "post"): "linkedin.post",
    ("facebook", "post"): "facebook.page.post",
    ("instagram", "post"): "instagram.post",
    ("facebook", "reply"): "facebook.comment.reply",
    ("instagram", "reply"): "instagram.comment.reply",
}


class SenderRegistry:
    def __init__(self, senders: list[Sender] | None = None) -> None:
        self._senders: list[Sender] = list(senders or [])

    def add(self, sender: Sender) -> None:
        self._senders.append(sender)

    def for_action(self, action_type: str) -> Sender | None:
        """The connected sender for an action type, if any."""
        return next((s for s in self._senders if action_type in s.action_types and s.is_connected()), None)

    def connected_action(self, platform: str, item_type: str) -> str | None:
        """The action type a draft would be sent with, if its platform is connected; else None (copy and paste)."""
        action = ACTION_FOR.get((platform, item_type))
        return action if action and self.for_action(action) else None

    def connections(self) -> list[dict]:
        return [
            {"label": s.label, "action_types": list(s.action_types), "connected": s.is_connected()}
            for s in self._senders
        ]


# The app's registry (set at startup), so tools can tell whether a platform is connected.
CURRENT = SenderRegistry()


def set_current(registry: SenderRegistry) -> None:
    global CURRENT
    CURRENT = registry
