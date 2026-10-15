"""What every API sender is (P3-01).

A sender is plain code, never AI: it takes one approved item and sends exactly its text (and
images) through one official API, then says what happened:
    sent      the platform accepted it (with the post's id and link)
    failed    the platform clearly refused it, so nothing was posted (safe to try again by hand)
    unclear   we can't tell (timeout, server error, lost connection): you check the platform
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import httpx

Outcome = Literal["sent", "failed", "unclear"]


@dataclass(frozen=True)
class Outgoing:
    """One approved item, ready to send."""

    item_id: int
    action_type: str  # e.g. linkedin.post
    platform: str
    item_type: str
    text: str  # exactly the text you approved
    images: tuple[Path, ...] = ()
    meta: dict = field(default_factory=dict)  # e.g. the comment a reply answers (P3-05)


@dataclass
class SendResult:
    outcome: Outcome
    detail: str = ""  # plain words: what happened
    remote_id: str = ""  # the platform's id for the post
    url: str = ""  # a link to it


class Sender(Protocol):
    label: str  # e.g. "LinkedIn"
    action_types: tuple[str, ...]  # what it can send, e.g. ("linkedin.post",)

    def is_connected(self) -> bool: ...

    async def send(self, out: Outgoing) -> SendResult: ...


def result_from_http_error(e: Exception, label: str) -> SendResult:
    """Turn an HTTP problem into "failed" (clearly refused: nothing posted) or "unclear"."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if 400 <= code < 500 and code not in (408, 409, 429):
            return SendResult("failed", f"{label} refused it (HTTP {code}): {_reason(e.response)}")
        if code == 429:
            return SendResult("failed", f"{label} says too many requests right now (HTTP 429); nothing was posted.")
        return SendResult("unclear", f"{label} had a problem (HTTP {code}); it may or may not have posted.")
    if isinstance(e, httpx.ConnectError):
        return SendResult("failed", f"Couldn't connect to {label}; nothing was sent.")
    if isinstance(e, httpx.TimeoutException):
        return SendResult("unclear", f"{label} didn't answer in time; it may or may not have posted.")
    return SendResult("unclear", f"Something went wrong while sending to {label} ({type(e).__name__}).")


def _reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or "no details"
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:200]
    return str(body.get("message") or body)[:200] if isinstance(body, dict) else str(body)[:200]
