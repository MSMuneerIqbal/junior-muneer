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


# Lines that are notes or labels, not part of the text to paste ("Status: awaiting approval", "Cover letter:").
_NOTES = re.compile(
    r"^\s*(approval card|status\s*:|recommendation\b|cover letter\s*:?\s*$|screening (questions?|answers?)\b|"
    r"notes?( to (you|muneer|the user))?\s*:|draft\s*:|p\.?s\.? for you|\[(insert|your name|add)[^\]]*\])",
    re.IGNORECASE | re.MULTILINE,
)


# Lines that list what you haven't done, or still need to "validate": they lose clients.
_A = "['’]"
_UNDERSELL = re.compile(
    rf"\b(i(?: have|{_A}ve) (?:not|never)\b|i haven{_A}?t\b|"
    rf"(?:no|i don{_A}?t have)(?: much| any| prior| direct| real)* experience|"
    rf"(?:i{_A}d|i would|i{_A}ll|i will) (?:still )?(?:need|have) to (?:validate|learn|confirm|figure out)|"
    rf"still needs? to (?:be )?validat|i{_A}?m (?:new to|not (?:sure|an expert))|i can{_A}?t (?:promise|guarantee))",
    re.IGNORECASE,
)


def undersells(text: str) -> list[str]:
    found = _UNDERSELL.search(text)
    if not found:
        return []
    return [
        f"Undersells you: “{found.group(0)}”. Don't list what you haven't done or still need to check; "
        "show your closest real work and ask the client about the unknowns."
    ]


_PLACEHOLDER = re.compile(r"\[(insert[^\]]*|your name|name|client name|company( name)?|link|url|add [^\]]*)\]", re.IGNORECASE)


def leftover_notes(text: str) -> list[str]:
    """Labels, notes or placeholders left in a draft: pasting them would look careless."""
    hole = _PLACEHOLDER.search(text)
    if hole:
        return [f"Has a placeholder to fill in: “{hole.group(0)}”. Write the real words or leave it out."]
    found = _NOTES.search(text)
    if not found:
        return []
    line = text[found.start() : text.find("\n", found.start()) if "\n" in text[found.start() :] else len(text)].strip()
    return [f"Has a note or label that isn't part of the text to paste: “{line[:60]}”. Leave only the text itself."]


def lint(text: str, playbook: Playbook, item_type: str = "post") -> list[str]:
    """Fast rule-based checks. Plain-English problems, empty when none."""
    if item_type == "post":
        issues = playbook.check(text)  # length, words, hashtags, links
    else:
        issues = [p for p in [too_long(text, playbook)] if p]
        if item_type in SHORT_KINDS and len(_HASHTAG.findall(text)) > MAX_SHORT_HASHTAGS:
            issues.append(f"A {item_type} doesn't need hashtags; use at most {MAX_SHORT_HASHTAGS}.")
    if item_type == "proposal":  # the playbook's length guide, as a hint
        words = len(text.split())
        low, high = playbook.words
        if words > high:
            issues.append(f"Long for a {playbook.label} proposal: {words} words, aim for {low} to {high}.")
        elif words < low:
            issues.append(f"Short for a {playbook.label} proposal: {words} words, aim for {low} to {high}.")
    issues.extend(red_lines(text, playbook.platform))
    issues.extend(leftover_notes(text))
    if item_type == "proposal" or playbook.platform in ("upwork", "fiverr"):
        issues.extend(undersells(text))
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
