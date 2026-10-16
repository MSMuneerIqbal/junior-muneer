"""Client messages (workflow E): you paste the conversation, the team drafts a reply, you send it.

Code reads the client's words for warning signs (another app, an email or phone number,
paying first, personal details), so the reply keeps everything on the platform and you're
warned, whatever the AI says.
"""

import re
from typing import Any

from junior.freelance.scam import scam_signs
from junior.writing.redlines import _APPS

PLATFORM_LABELS = {"upwork": "Upwork", "fiverr": "Fiverr"}

# In a conversation with you, any clear app name is worth a warning (never a skip): "it's easier
# to talk on WhatsApp". Job posts use the strict check, as many jobs are about building such bots.
_APP_NAMES = re.compile(
    r"\b(whats\s?app|telegram|skype|discord|wechat|viber|google meet|zoom (?:call|meeting|link)|signal app)\b",
    re.IGNORECASE,
)


def is_client_message(paste: dict[str, Any] | None) -> bool:
    return bool(paste) and paste["kind"] == "client_message" and paste["platform"] in PLATFORM_LABELS


def client_warnings(paste: dict[str, Any] | None) -> list[str]:
    """Warning signs in a pasted Upwork or Fiverr client message, found by code."""
    if not is_client_message(paste):
        return []
    text = paste["text"]
    signs = scam_signs(text)
    app = _APP_NAMES.search(text)
    if app and not _APPS.search(text):
        label = PLATFORM_LABELS[paste["platform"]]
        signs.insert(0, f"Mentions {app.group(0)}: if they want to talk, share files or pay there, keep it on {label}.")
    return signs


def reply_notes(paste: dict[str, Any], user_name: str) -> str:
    """What the writing team must know to answer a client conversation."""
    label = PLATFORM_LABELS[paste["platform"]]
    notes = [
        f"The text below is the conversation so far with a client on {label}. Messages from {user_name} "
        "are already sent: answer the client's newest message, and don't repeat what's already been said."
    ]
    if warnings := client_warnings(paste):
        notes.append(
            "Warning signs code found in the client's words: " + " ".join(warnings) + " Politely keep everything "
            f"on {label} (messages, calls, files and payment), and never repeat their contact details."
        )
    return "\n".join(notes)
