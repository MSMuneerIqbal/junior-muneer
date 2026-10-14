"""Humanizer: rewrites a correct post so it reads like the owner typed it, in simple natural English."""

from ..llm import ask
from ..style import AI_PHRASES
from .common import Brief, Humanized, about_owner, task_block

SYSTEM = """You are the Humanizer on {name}'s social media team. You get a post that is correct but may sound stiff or machine-written. Make it read like {name} typed it on their own phone.

{about}

How to rewrite:
- Keep the meaning, every fact and the main point. Never add new claims.
- Use everyday words and contractions (I'm, it's, don't). Small informal touches are good.
- Mix short and medium sentences. Real people don't write in perfect patterns or neat lists of three.
- Cut filler, hype and phrases that sound like AI, for example: {phrases}.
- Stay inside the platform's length limit and hashtag rules."""


def humanize(brief: Brief, text: str, issues: list[str] | None = None) -> Humanized:
    prompt = f"{task_block(brief)}\n\nPost to rewrite:\n<post>\n{text}\n</post>"
    if issues:
        fixes = "\n".join(f"- {issue}" for issue in issues)
        prompt += f"\n\nThe final check still found these problems. Fix all of them:\n{fixes}"
    system = SYSTEM.format(
        name=brief.profile.name,
        about=about_owner(brief.profile),
        phrases=", ".join(f'"{p}"' for p in AI_PHRASES[:15]),
    )
    return ask("humanizer", system, prompt, Humanized)
