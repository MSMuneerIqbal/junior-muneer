"""Skills (P10-02): one instruction file per kind of work in skills/, like Claude's skills.

    ---
    name: cv_review                     # must match the file name (skills/cv_review.md)
    description: Review a CV for a job, a scholarship or a university; what to fix, in order.
    for: [junior_muneer, documents_agent]   # optional: only these agents see it (default: every agent with skills)
    ---
    The instructions, in Markdown: steps, what to check, the shape of the result.

An agent with the `skills` tool sees only the list (name + description) in its instructions and loads the one that fits
with `use_skill`, so its own instructions stay short and each kind of work comes out the same way. You can add one from
chat ("make a skill for my weekly client report"): `save_skill`, only from your own words. A broken skill stops
startup with a clear error, like a broken agent file or playbook.

    GET /api/skills   every skill (name, description, who sees it)
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import APIRouter

from junior.config import REPO_DIR

router = APIRouter()

SKILLS_DIR = REPO_DIR / "skills"
NOT_SKILL_FILES = {"README.md"}
_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
_FIELDS = {"name", "description", "for"}
MIN_INSTRUCTIONS = 40
MAX_INSTRUCTIONS = 20_000


class SkillError(Exception):
    """A skill file is broken. The message names the file and the problem."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    agents: tuple[str, ...] = ()  # empty: every agent with the skills tool

    def for_agent(self, agent: str) -> bool:
        return not self.agents or agent in self.agents


def parse_skill(text: str, filename: str) -> Skill:
    def fail(msg: str) -> SkillError:
        return SkillError(f"skills/{filename}: {msg}")

    match = _HEADER.match(text.replace("\r\n", "\n"))
    if not match:
        raise fail("it must start with a --- header (name, description) and a closing ---.")
    try:
        header = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise fail(f"the header isn't valid YAML: {e}") from None
    if not isinstance(header, dict):
        raise fail("the header must be name: value lines.")
    if unknown := set(header) - _FIELDS:
        raise fail(f"unknown field(s) {sorted(unknown)}; allowed: {sorted(_FIELDS)}.")
    name = header.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise fail("'name' must be lowercase letters, digits and _ (2 to 50), like cv_review.")
    if f"{name}.md" != filename:
        raise fail(f"'name' is {name!r} but the file is {filename!r}; they must match.")
    description = header.get("description")
    if not isinstance(description, str) or not 10 <= len(description.strip()) <= 300:
        raise fail("'description' is needed: one line (10 to 300 characters) saying when to use it.")
    agents = header.get("for") or []
    if not isinstance(agents, list) or not all(isinstance(a, str) and _NAME.match(a) for a in agents):
        raise fail("'for' must be a list of agent names, like [junior_muneer, documents_agent].")
    instructions = match.group(2).strip()
    if len(instructions) < MIN_INSTRUCTIONS:
        raise fail(f"the instructions under the header are missing or too short (at least {MIN_INSTRUCTIONS} characters).")
    if len(instructions) > MAX_INSTRUCTIONS:
        raise fail(f"the instructions are over {MAX_INSTRUCTIONS:,} characters; split it into two skills.")
    return Skill(name, " ".join(description.split()), instructions, tuple(agents))


def load_skills(folder: Path | None = None) -> dict[str, Skill]:
    folder = folder or SKILLS_DIR
    if not folder.is_dir():
        return {}
    skills = {}
    for path in sorted(folder.glob("*.md")):
        if path.name in NOT_SKILL_FILES:
            continue
        skill = parse_skill(path.read_text(encoding="utf-8"), path.name)
        skills[skill.name] = skill
    return skills


def skills_list(agent: str, folder: Path | None = None) -> str:
    """The skills this agent may load, one line each, for its instructions."""
    lines = [f"- `{s.name}`: {s.description}" for s in load_skills(folder).values() if s.for_agent(agent)]
    return "\n".join(lines) or "- (none yet)"


def save_skill(name: str, description: str, instructions: str, folder: Path | None = None) -> Path:
    """Write a new skill file (checked exactly like the ones read at startup). Raises SkillError."""
    folder = folder or SKILLS_DIR
    name = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    filename = f"{name}.md"
    text = f"---\nname: {name}\ndescription: {yaml.safe_dump(description.strip(), width=1000).strip()}\n---\n{instructions.strip()}\n"
    parse_skill(text, filename)
    path = folder / filename
    if path.exists():
        raise SkillError(f"skills/{filename} already exists; pick another name (or edit that file).")
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@router.get("/api/skills")
def get_skills() -> list[dict]:
    return [{"name": s.name, "description": s.description, "for": list(s.agents) or "every agent with skills"}
            for s in load_skills().values()]
