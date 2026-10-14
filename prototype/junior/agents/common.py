"""What every specialist agent shares: the brief for one post and the shapes of their answers."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from ..config import Profile
from ..platforms import Platform
from ..style import VOICE_RULES


@dataclass
class Brief:
    """Everything the team needs to know to work on one post."""

    profile: Profile
    platform: Platform
    topic: str
    notes: str = ""
    feedback: str = ""          # the owner's change request on an earlier version
    previous_text: str = ""     # that earlier version
    examples: list[str] = field(default_factory=list)  # posts the owner approved before


def about_owner(profile: Profile) -> str:
    return f"About {profile.name}:\n{profile.as_text()}\n\nVoice rules for every post:\n{VOICE_RULES}"


def task_block(brief: Brief) -> str:
    p = brief.platform
    parts = [
        f"Platform: {p.name}",
        f"Length: {p.length_hint} (hard limit {p.max_chars} characters)",
        f"Style: {p.style}",
        f"Topic: {brief.topic}",
        f"Extra notes from {brief.profile.name}: {brief.notes or 'none'}",
    ]
    if brief.examples:
        samples = "\n\n".join(f"<example>\n{text}\n</example>" for text in brief.examples)
        parts.append(
            f"Posts {brief.profile.name} approved before. Match this voice, but don't reuse their content:\n{samples}"
        )
    if brief.feedback:
        parts.append(
            f"{brief.profile.name} reviewed an earlier version and asked for changes.\n"
            f"<earlier_version>\n{brief.previous_text}\n</earlier_version>\n"
            f"Their feedback: {brief.feedback}"
        )
    return "\n\n".join(parts)


class Draft(BaseModel):
    text: str = Field(description="The full post, exactly as it should be published.")
    visual_idea: str = Field(description="One sentence: an image or simple graphic that would suit this post.")


class Review(BaseModel):
    score: int = Field(description="Overall quality from 1 (bad) to 10 (ready to publish as-is).")
    invented_facts: list[str] = Field(
        description="Claims about the owner that the profile or notes do not support. Empty if none."
    )
    issues: list[str] = Field(
        description="Specific, fixable problems. Quote the exact words that need to change. Empty if none."
    )
    passes: bool = Field(description="True only if score is 8 or more and there are no invented facts.")


class Humanized(BaseModel):
    text: str = Field(description="The rewritten post, exactly as it should be published.")
    changes: list[str] = Field(description="Short notes on what you changed.")


class Idea(BaseModel):
    platform: Literal["linkedin", "facebook", "instagram", "x"]
    title: str = Field(description="The post topic in one short line.")
    angle: str = Field(description="The specific story, example or point the post should make.")
    why: str = Field(description="One sentence on why this helps win clients.")


class IdeaList(BaseModel):
    ideas: list[Idea]
