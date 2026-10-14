"""Social Media Manager: plans what to post so the owner never starts from a blank page."""

from ..config import Profile
from ..llm import ask
from ..platforms import Platform
from .common import Idea, IdeaList, about_owner

SYSTEM = """You are the Social Media Manager for {name}, a freelancer. You plan posts that help {name} win clients by showing real work, lessons and personality.

Good ideas are specific: a real project from the profile, a mistake and what it taught, a quick practical tip, a before and after, an honest opinion about the industry. Avoid generic advice anyone could post.

{about}"""


def suggest(profile: Profile, platforms: list[Platform], count: int, focus: str, recent: list[str]) -> list[Idea]:
    names = ", ".join(f"{p.key} ({p.name})" for p in platforms)
    prompt = f"Suggest {count} post ideas, spread across these platforms: {names}."
    if focus:
        prompt += f"\n\nFocus for this batch: {focus}"
    if recent:
        done = "\n".join(f"- {topic}" for topic in recent)
        prompt += f"\n\nAlready posted or drafted. Don't repeat these:\n{done}"
    allowed = {p.key for p in platforms}
    result = ask("planner", SYSTEM.format(name=profile.name, about=about_owner(profile)), prompt, IdeaList)
    return [idea for idea in result.ideas if idea.platform in allowed][:count]
