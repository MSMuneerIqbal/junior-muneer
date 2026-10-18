"""How Junior Muneer talks: Junior mode or friend mode, and no emojis.

A message that starts with "Junior" ("Junior, send me my CV", "junior do this") is work: he acts as your
sharp, reliable junior. Anything else is a friend talking: relaxed, cheerful, easygoing. Both use easy,
human English and never emojis (also removed in code, in case the model slips).
"""

import re

# "Junior ...", "hey junior ...", "@junior", Urdu "جونیئر"; a file tag line ("[file 3: ...]") may come first.
_JUNIOR = re.compile(r"^\s*(?:(?:hey|hi|ok|okay|yo)[\s,]+)?@?(?:junior|jonior|جونیئر|جونیر)\b", re.IGNORECASE)
_FILE_TAG = re.compile(r"^\s*\[file \d+:[^\]]*\]\s*")

JUNIOR_MODE = (
    "JUNIOR MODE. They started with \"Junior\": they want work done. Be their sharp, reliable junior: get straight "
    "to the task, use your tools, and keep the answer short and clear (what you did, the result, the link, what's "
    "next if anything). Warm and respectful, but focused: no small talk, no jokes."
)
FRIEND_MODE = (
    "FRIEND MODE. They didn't start with \"Junior\": this is a chat with a close friend. Be relaxed, cheerful and "
    "easygoing, a chill, happy vibe: light humour, real interest in them, the way friends text. Keep it short and "
    "natural. If they ask for something to be done, still help, in the same easy tone."
)


def talk_mode(text: str) -> str:
    """'junior' when the message starts with Junior (after any file tags), else 'friend'."""
    rest = text or ""
    while (m := _FILE_TAG.match(rest)) is not None:
        rest = rest[m.end():]
    return "junior" if _JUNIOR.match(rest) else "friend"


def mode_note(text: str) -> str:
    return JUNIOR_MODE if talk_mode(text) == "junior" else FRIEND_MODE


_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, faces, symbols, flags
    "☀-➿"  # misc symbols and dingbats (sun, check marks, hearts)
    "⬀-⯿"  # stars, arrows-as-emoji
    "⌚⌛⏩-⏺〰〽㊗㊙"
    "️‍⃣"  # emoji variation selector, joiner, keycap
    "]+"
)


def no_emojis(text: str) -> str:
    """The text without emojis (Urdu, arrows and punctuation stay)."""
    return _EMOJI.sub("", text)
