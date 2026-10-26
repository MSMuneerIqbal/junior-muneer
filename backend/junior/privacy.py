"""Small shared credential check for persistent user-authored instructions and facts."""

import re


def credential_present(text: str) -> bool:
    from junior.senders.guard import NEVER_SEND
    return bool(any(pattern.search(text) for pattern, _ in NEVER_SEND) or re.search(r"\bAIza[\w-]{25,}", text))


def safe_error(text: str) -> str:
    return "Sensitive input omitted." if credential_present(text) else text
