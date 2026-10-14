"""Post Writer: writes the first draft and fixes it when the checker sends it back."""

from ..llm import ask
from .common import Brief, Draft, about_owner, task_block

SYSTEM = """You are the Post Writer on {name}'s social media team. You write posts as {name}, in the first person, to help {name} win freelance clients by showing real skill and personality.

{about}"""


def _system(brief: Brief) -> str:
    return SYSTEM.format(name=brief.profile.name, about=about_owner(brief.profile))


def write(brief: Brief) -> Draft:
    prompt = f"Write one post.\n\n{task_block(brief)}"
    return ask("writer", _system(brief), prompt, Draft)


def revise(brief: Brief, draft: str, issues: list[str]) -> Draft:
    problems = "\n".join(f"- {issue}" for issue in issues)
    prompt = (
        f"{task_block(brief)}\n\n"
        f"Your draft:\n<post>\n{draft}\n</post>\n\n"
        f"The quality checker sent it back with these problems:\n{problems}\n\n"
        "Rewrite the post so every problem is fixed. Keep what already works."
    )
    return ask("writer", _system(brief), prompt, Draft)
