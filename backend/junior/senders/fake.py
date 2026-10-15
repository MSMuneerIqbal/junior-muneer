"""A fake sender for tests and FAKE_AI mode: nothing leaves your PC.

In FAKE_AI mode it stands in for the Facebook Page, so the whole approve-and-post flow can be
tried without any account. Text containing "[fail]" is refused and "[unclear]" gets no clear
answer, to try those paths too.
"""

from junior.senders.base import Outgoing, SendResult


class FakeSender:
    def __init__(self, label: str = "Facebook Page (fake)", action_types: tuple[str, ...] = ("facebook.page.post",)):
        self.label = label
        self.action_types = action_types
        self.sent: list[Outgoing] = []

    def is_connected(self) -> bool:
        return True

    async def send(self, out: Outgoing) -> SendResult:
        if "[fail]" in out.text:
            return SendResult("failed", f"{self.label} refused it (fake failure).")
        if "[unclear]" in out.text:
            return SendResult("unclear", f"{self.label} didn't answer clearly (fake).")
        self.sent.append(out)
        n = len(self.sent)
        return SendResult("sent", f"Posted on {self.label}.", remote_id=f"fake-{out.item_id}-{n}",
                          url=f"https://example.invalid/fake-posts/{out.item_id}")
