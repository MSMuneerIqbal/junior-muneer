"""App settings (from .env) and the owner's profile (from my_profile.toml)."""

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("CLAUDE_EFFORT", "medium")
    host: str = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port: int = int(os.getenv("DASHBOARD_PORT", "8000"))
    username: str = os.getenv("DASHBOARD_USERNAME", "admin")
    password: str = os.getenv("DASHBOARD_PASSWORD", "")
    db_path: Path = ROOT / "data" / "junior.db"
    profile_path: Path = ROOT / "my_profile.toml"


settings = Settings()


def has_api_credentials() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


class ProfileError(Exception):
    pass


@dataclass
class Profile:
    name: str
    headline: str = ""
    about: str = ""
    services: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    audience: str = ""
    proof: list[str] = field(default_factory=list)
    voice: str = ""
    avoid: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        """The profile as plain text for the agents' prompts."""
        lines = [f"Name: {self.name}"]
        if self.headline:
            lines.append(f"What I do: {self.headline}")
        if self.about:
            lines.append(f"About me:\n{self.about.strip()}")
        if self.services:
            lines.append("Services I sell:\n" + _bullets(self.services))
        if self.skills:
            lines.append("Skills and tools: " + ", ".join(self.skills))
        if self.audience:
            lines.append(f"Who I want to reach: {self.audience}")
        if self.proof:
            lines.append("Real work and results (the only facts you may use):\n" + _bullets(self.proof))
        if self.voice:
            lines.append(f"My voice:\n{self.voice.strip()}")
        if self.avoid:
            lines.append("Never do this:\n" + _bullets(self.avoid))
        if self.hashtags:
            lines.append("Hashtags I like: " + " ".join(self.hashtags))
        return "\n\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def load_profile() -> Profile:
    """Read my_profile.toml fresh each time, so edits apply without a restart."""
    try:
        with open(settings.profile_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ProfileError(f"{settings.profile_path.name} is missing.") from None
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"{settings.profile_path.name} has a typo: {e}") from None
    if not str(data.get("name", "")).strip():
        raise ProfileError(f'Set your name in {settings.profile_path.name} (name = "...").')
    known = {f.name for f in fields(Profile)}
    return Profile(**{k: v for k, v in data.items() if k in known})
