"""The Polisher: content Junior writes for you to send or keep (emails, Google Docs, messages, notes) is rewritten
by agents/polisher.md before it's created or sent, so it reads like a careful human wrote it.

Code checks around the AI:
    - AI signs (words, openers, long dashes, emojis, "not just X but Y") are found in code; if any are left, the
      Polisher gets one more try with the list;
    - every link, email address and number in your draft must still be there (polishing never changes facts);
      if one is lost, the draft is kept as it was, with only safe fixes (long dashes, emojis).
Social posts and proposals go through the writing team's Humanizer instead.
"""

import re
import uuid

from pydantic import BaseModel, Field

from junior.writing.style import AI_PHRASES

MIN_CHARS = 120  # shorter bits ("OK, done") aren't worth a rewrite
MAX_CHARS = 30_000

EXTRA_SIGNS = [
    "i hope this email finds you well", "i hope this message finds you well", "i wanted to reach out",
    "i trust you are doing well", "please don't hesitate", "please do not hesitate", "feel free to reach out",
    "i hope this helps", "certainly!", "great question", "additionally,", "comprehensive", "crucial", "pivotal",
    "utilize", "facilitate", "foster",
]
_DASH = re.compile(r"\s*[—–]\s*")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_NOT_JUST = re.compile(r"\bnot (just|only)\b[^.!?\n]*\b(but|it's|it is)\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)>\]]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")


class Polished(BaseModel):
    text: str
    changes: list[str] = Field(default_factory=list)


def ai_signs(text: str) -> list[str]:
    """What still sounds machine-written, in plain words."""
    low = text.lower()
    found = [p for p in [*AI_PHRASES, *EXTRA_SIGNS] if re.search(rf"(?<!\w){re.escape(p)}", low)]
    signs = [f'"{p}"' for p in found]
    if _DASH.search(text):
        signs.append("long dashes")
    if _EMOJI.search(text):
        signs.append("emojis")
    if _NOT_JUST.search(text):
        signs.append('"not just X, but Y"')
    return signs


def safe_fixes(text: str) -> str:
    """Fixes code can make on its own: long dashes become commas, emojis go."""
    text = _DASH.sub(", ", text)
    text = _EMOJI.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).replace(" ,", ",")


def facts(text: str) -> set[str]:
    """Links, email addresses and numbers: these must survive polishing."""
    links = {u.rstrip(".,;:!?") for u in _URL.findall(text)}
    emails = {e.lower() for e in _EMAIL.findall(text)}
    plain = _EMAIL.sub(" ", _URL.sub(" ", text))
    return links | emails | {n.replace(",", "") for n in _NUMBER.findall(plain)}


def lost_facts(before: str, after: str) -> list[str]:
    kept = facts(after)
    return sorted(f for f in facts(before) if f not in kept)


def _prompt(text: str, kind: str, fix: list[str] | None = None) -> str:
    again = f"\n\nYour last version still had: {', '.join(fix)}. Fix every one, and keep every fact." if fix else ""
    return f"## What it is\n{kind}{again}\n\n## The content\n<content>\n{text}\n</content>"


async def polish(text: str, kind: str, context) -> str:
    """The content, polished (or as it was, with safe fixes, when polishing can't be trusted)."""
    if len(text.strip()) < MIN_CHARS or len(text) > MAX_CHARS or context.helpers is None:
        return safe_fixes(text)
    helpers = context.helpers
    best, notes = text, []
    problems: list[str] | None = None
    for _attempt in range(2):
        try:
            out: Polished = await helpers.run_structured("polisher", _prompt(text, kind, problems), context, Polished)
        except Exception:  # noqa: BLE001 - polishing is a bonus: never lose the content over it
            break
        candidate = out.text.strip()
        lost = lost_facts(text, candidate)
        if candidate and not lost:
            best, notes = candidate, out.changes
            problems = ai_signs(candidate)
            if not problems:
                break
        else:
            problems = [f"you dropped {', '.join(lost[:5])}"] if lost else ["an empty answer"]
    best = safe_fixes(best)
    context.emit({
        "type": "step", "id": f"polish-{uuid.uuid4().hex[:8]}", "kind": "team", "status": "done",
        "label": f"Polisher: made the {kind} read like you wrote it" if best != safe_fixes(text) else f"Polisher: kept the {kind} as written",
        "notes": notes[:3] or None,
    })
    return best
