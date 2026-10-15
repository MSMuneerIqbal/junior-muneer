"""Your profile: the only source of facts for anything written about you.

    GET /api/profile   your profile
    PUT /api/profile   save it (each change is in the audit log)
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from junior.audit import audit
from junior.settings_store import get_setting, set_setting

router = APIRouter()

PLATFORM_KEYS = ("linkedin", "facebook", "instagram", "x")


class Profile(BaseModel):
    headline: str = Field(default="", max_length=200)  # what you do, in one line
    about: str = Field(default="", max_length=3000)
    services: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    rates: str = Field(default="", max_length=500)
    proof: list[str] = Field(default_factory=list)  # real projects and results
    audience: str = Field(default="", max_length=1000)  # who you want to reach
    voice: str = Field(default="", max_length=1000)  # how you like to sound
    avoid: list[str] = Field(default_factory=list)  # things never to say or do
    hashtags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)  # where you post
    links: list[str] = Field(default_factory=list)  # portfolio, GitHub, Upwork...
    email: str = Field(default="", max_length=200)  # your own address (used from the email phase)
    phone: str = Field(default="", max_length=50)  # kept for later; never put into prompts
    location: str = Field(default="", max_length=200)
    languages: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.headline or self.about or self.services or self.proof)


class ProfileMissing(Exception):
    """The writing team needs a profile before it can write about you."""


def _clean(items: list[str]) -> list[str]:
    return [i.strip() for i in items if i and i.strip()][:50]


def load_profile() -> Profile:
    return Profile(**(get_setting("profile") or {}))


def profile_text(name: str | None = None) -> str:
    """The profile as plain text for the writing team's prompts."""
    p = load_profile()
    if p.is_empty():
        raise ProfileMissing(
            "Your profile is empty, so I can't write about you without inventing things. "
            "Fill it in on the Profile page first (what you do, services, real projects and results)."
        )
    name = name or get_setting("user_name")

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items)

    parts = [f"Name: {name}"]
    if p.location:
        parts.append(f"Location: {p.location}")
    if p.languages:
        parts.append("Languages: " + ", ".join(p.languages))
    if p.headline:
        parts.append(f"What I do: {p.headline}")
    if p.about:
        parts.append(f"About me:\n{p.about.strip()}")
    if p.services:
        parts.append("Services I sell:\n" + bullets(p.services))
    if p.skills:
        parts.append("Skills and tools: " + ", ".join(p.skills))
    if p.rates:
        parts.append(f"Rates: {p.rates}")
    if p.proof:
        parts.append("Real projects and results (the ONLY facts you may use):\n" + bullets(p.proof))
    if p.audience:
        parts.append(f"Who I want to reach: {p.audience}")
    if p.voice:
        parts.append(f"How I like to sound: {p.voice}")
    if p.avoid:
        parts.append("Never say or do:\n" + bullets(p.avoid))
    if p.hashtags:
        parts.append("Hashtags I use: " + " ".join(h if h.startswith("#") else f"#{h}" for h in p.hashtags))
    if p.links:
        parts.append("Links: " + ", ".join(p.links))
    return "\n\n".join(parts)


@router.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    return load_profile()


@router.put("/api/profile", response_model=Profile)
def put_profile(body: Profile) -> Profile:
    before = load_profile()
    cleaned = body.model_copy(
        update={
            "services": _clean(body.services),
            "skills": _clean(body.skills),
            "proof": _clean(body.proof),
            "avoid": _clean(body.avoid),
            "hashtags": _clean(body.hashtags),
            "links": _clean(body.links),
            "languages": _clean(body.languages),
            "platforms": [p for p in body.platforms if p in PLATFORM_KEYS],
        }
    )
    set_setting("profile", cleaned.model_dump())
    changed = [k for k in Profile.model_fields if getattr(before, k) != getattr(cleaned, k)]
    if changed:
        audit("setting", "profile", detail={"changed": changed})
    return cleaned


def profile_for_chat() -> str:
    """Your profile for Junior Muneer's own instructions, so he knows you in every chat."""
    try:
        return profile_text()
    except ProfileMissing:
        return "(Not filled in yet. If it matters, suggest filling in the Profile page.)"
