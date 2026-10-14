"""The shared voice rules, plus quick automatic checks for text that sounds machine-written."""

import re

from .platforms import Platform

VOICE_RULES = """\
- Simple, plain English. Short sentences and common words. A reader whose first language is not English should understand every line.
- Sound like a real person talking to a friend or a client, not a brochure or an ad.
- Use "I" and "you". Use real, specific details from the profile instead of general claims.
- No hype, buzzwords or cliches.
- No long dashes (em dash or en dash). Use a comma, a full stop or "and" instead.
- Do not open with a question hook like "Ever wondered...?" or "Did you know...?".
- At most 2 emojis, and only if they fit the platform. No emoji bullet lists.
- No generic engagement bait like "What do you think? Let me know in the comments!". A specific, real question is fine.
- Never invent facts, numbers, clients, tools or results that are not in the profile or the notes."""

# Words and phrases that make a post read as AI-written. The checker gets these as hints.
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


def over_limit(text: str, platform: Platform) -> str:
    if len(text) > platform.max_chars:
        return f"Too long: {len(text)} characters, the {platform.name} limit is {platform.max_chars}."
    return ""


def lint(text: str, platform: Platform) -> list[str]:
    """Fast rule-based checks. Returns a list of plain-English problems (empty if none)."""
    issues = []
    if too_long := over_limit(text, platform):
        issues.append(too_long)
    if "—" in text or "–" in text:
        issues.append("Uses long dashes. Most people don't type these; use a comma or a full stop.")
    found = [p for p in AI_PHRASES if re.search(rf"\b{re.escape(p)}\b", text, re.IGNORECASE)]
    if found:
        issues.append("Sounds like AI: " + ", ".join(f'"{p}"' for p in found) + ".")
    if _NOT_JUST.search(text):
        issues.append('Uses the "not just X, but Y" pattern, which reads as AI-written.')
    hashtags = re.findall(r"#\w+", text)
    if len(hashtags) > platform.max_hashtags:
        issues.append(f"{len(hashtags)} hashtags; use at most {platform.max_hashtags} on {platform.name}.")
    if len(_EMOJI.findall(text)) > 2:
        issues.append("Too many emojis; use 2 or fewer.")
    if text.count("!") > 2:
        issues.append("Too many exclamation marks; it sounds forced.")
    return issues
