"""Quick automatic checks for text that sounds machine-written (from the prototype).

They run before the Checker and are passed to it as hints; hard limits (too long)
also stop a draft from passing on their own.
"""

import re

from junior.playbooks import Playbook
from junior.writing.redlines import red_lines

# Words and phrases that make a post read as AI-written.
AI_PHRASES = [
    "delve", "dive into", "deep dive", "in today's fast-paced", "in today's digital",
    "ever-evolving", "game-changer", "game changer", "unlock", "unleash", "elevate",
    "leverage", "seamless", "seamlessly", "robust", "cutting-edge", "revolutionize",
    "harness", "embark", "tapestry", "testament", "landscape", "realm", "furthermore",
    "moreover", "it's important to note", "in conclusion", "navigate the", "navigating",
    "supercharge", "empower", "synergy", "transformative", "look no further",
    "whether you're", "let's dive", "buckle up", "here's the thing", "the secret sauce",
]

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_NOT_JUST = re.compile(r"\bnot (just|only)\b[^.!?\n]*\b(but|it's|it is)\b", re.IGNORECASE)
_HASHTAG = re.compile(r"(?<!\w)#\w+")
_QUESTION_HOOK = re.compile(r"^\s*(ever wondered|did you know|have you ever)\b", re.IGNORECASE)

# Comments, replies and messages are short, whatever the platform's post length.
SHORT_KINDS = {"comment", "reply", "message"}
MAX_SHORT_HASHTAGS = 1


def too_long(text: str, playbook: Playbook) -> str:
    if len(text) > playbook.max_chars:
        return f"Too long for {playbook.label}: {len(text)} characters, the limit is {playbook.max_chars}."
    return ""


def lint(text: str, playbook: Playbook, item_type: str = "post") -> list[str]:
    """Fast rule-based checks. Plain-English problems, empty when none."""
    if item_type == "post":
        issues = playbook.check(text)  # length, words, hashtags, links
    else:
        issues = [p for p in [too_long(text, playbook)] if p]
        if item_type in SHORT_KINDS and len(_HASHTAG.findall(text)) > MAX_SHORT_HASHTAGS:
            issues.append(f"A {item_type} doesn't need hashtags; use at most {MAX_SHORT_HASHTAGS}.")
    issues.extend(red_lines(text, playbook.platform))
    if "—" in text or "–" in text:
        issues.append("Uses long dashes. Most people don't type these; use a comma or a full stop.")
    found = [p for p in AI_PHRASES if re.search(rf"\b{re.escape(p)}\b", text, re.IGNORECASE)]
    if found:
        issues.append("Sounds like AI: " + ", ".join(f'"{p}"' for p in found) + ".")
    if _NOT_JUST.search(text):
        issues.append('Uses the "not just X, but Y" pattern, which reads as AI-written.')
    if _QUESTION_HOOK.search(text):
        issues.append('Opens with a question hook ("Ever wondered", "Did you know"); start with the point.')
    if len(_EMOJI.findall(text)) > 2:
        issues.append("Too many emojis; use 2 or fewer.")
    if text.count("!") > 2:
        issues.append("Too many exclamation marks; it sounds forced.")
    return issues
