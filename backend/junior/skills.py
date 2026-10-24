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

import hashlib
import os
import re
import tempfile
from threading import RLock
from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from junior.audit import audit
from junior.config import REPO_DIR

router = APIRouter()

SKILLS_DIR = Path(os.environ.get("JUNIOR_SKILLS_DIR") or REPO_DIR / "skills")
_LOCK = RLock()
NOT_SKILL_FILES = {"README.md"}
_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
_FIELDS = {"name", "description", "for"}
MIN_INSTRUCTIONS = 40
MAX_INSTRUCTIONS = 20_000


class SkillError(Exception):
    """A skill file is broken. The message names the file and the problem."""


class SkillNotFound(SkillError):
    pass


class SkillConflict(SkillError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    agents: tuple[str, ...] = ()  # empty: every agent with the skills tool
    revision: str = ""

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
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise fail("'name' must be lowercase letters, digits and _ (2 to 50), like cv_review.")
    if f"{name}.md" != filename:
        raise fail(f"'name' is {name!r} but the file is {filename!r}; they must match.")
    description = header.get("description")
    if not isinstance(description, str) or not 10 <= len(description.strip()) <= 300:
        raise fail("'description' is needed: one line (10 to 300 characters) saying when to use it.")
    agents = header.get("for") or []
    if not isinstance(agents, list) or not all(isinstance(a, str) and _NAME.fullmatch(a) for a in agents):
        raise fail("'for' must be a list of agent names, like [junior_muneer, documents_agent].")
    instructions = match.group(2).strip()
    if len(instructions) < MIN_INSTRUCTIONS:
        raise fail(f"the instructions under the header are missing or too short (at least {MIN_INSTRUCTIONS} characters).")
    if len(instructions) > MAX_INSTRUCTIONS:
        raise fail(f"the instructions are over {MAX_INSTRUCTIONS:,} characters; split it into two skills.")
    return Skill(name, " ".join(description.split()), instructions, tuple(agents),
                 hashlib.sha256(text.encode("utf-8")).hexdigest())


def _path(name: str, folder: Path) -> Path:
    reserved = {"readme", "con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    if not _NAME.fullmatch(name) or name in reserved:
        raise SkillError("Use 2 to 50 lowercase letters, digits and underscores for the skill name.")
    path = folder / f"{name}.md"
    if path.is_symlink() or path.resolve().parent != folder.resolve():
        raise SkillError("Skill files must be ordinary files inside the skills folder, not links.")
    return path


def _read(name: str, folder: Path) -> Skill:
    path = _path(name, folder)
    try:
        if path.stat().st_size > 128_000:
            raise SkillError(f"skills/{path.name}: file is too large.")
        return parse_skill(path.read_text(encoding="utf-8"), path.name)
    except FileNotFoundError:
        raise SkillNotFound(f"Skill {name!r} was not found.") from None
    except (OSError, UnicodeError):
        raise SkillError(f"Could not read skills/{path.name}.") from None


def load_skills(folder: Path | None = None) -> dict[str, Skill]:
    folder = folder or SKILLS_DIR
    if not folder.is_dir():
        return {}
    skills = {}
    with _LOCK:
        for path in sorted(folder.glob("*.md")):
            if path.name in NOT_SKILL_FILES:
                continue
            skill = _read(path.stem, folder)
            skills[skill.name] = skill
    return skills


def skills_list(agent: str, folder: Path | None = None) -> str:
    """The skills this agent may load, one line each, for its instructions."""
    lines = [f"- `{s.name}`: {s.description}" for s in load_skills(folder).values() if s.for_agent(agent)]
    return "\n".join(lines) or "- (none yet)"


def save_skill(name: str, description: str, instructions: str, folder: Path | None = None,
               *, agents: tuple[str, ...] = (), revision: str | None = None) -> Path:
    """Write a new skill file (checked exactly like the ones read at startup). Raises SkillError."""
    folder = folder or SKILLS_DIR
    name = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    filename = f"{name}.md"
    header = {"name": name, "description": description.strip()}
    if agents:
        header["for"] = list(agents)
    text = f"---\n{yaml.safe_dump(header, sort_keys=False, allow_unicode=True, width=1000)}---\n{instructions.strip()}\n"
    parse_skill(text, filename)
    with _LOCK:
        path = _path(name, folder)
        if revision is None:
            if path.exists():
                raise SkillConflict(f"skills/{filename} already exists; pick another name (or edit that file).")
        elif _read(name, folder).revision != revision:
            raise SkillConflict("This skill changed since you opened it. Reopen it before saving or deleting.")
        folder.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=folder,
                                             suffix=".tmp", delete=False) as f:
                temporary = Path(f.name)
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            _path(name, folder)  # refuse a link swapped in while writing
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return path


def delete_skill(name: str, revision: str, folder: Path | None = None) -> None:
    folder = folder or SKILLS_DIR
    with _LOCK:
        if _read(name, folder).revision != revision:
            raise SkillConflict("This skill changed since you opened it. Reopen it before saving or deleting.")
        _path(name, folder).unlink()


def _out(skill: Skill) -> dict:
    return {"name": skill.name, "description": skill.description, "instructions": skill.instructions,
            "for": list(skill.agents), "revision": skill.revision}


def _http_error(error: SkillError) -> HTTPException:
    status = 404 if isinstance(error, SkillNotFound) else 409 if isinstance(error, SkillConflict) else 422
    return HTTPException(status, str(error))


class SkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=300)
    instructions: str = Field(max_length=MAX_INSTRUCTIONS)
    agents: list[str] = Field(default_factory=list, alias="for", max_length=50)


class SkillCreate(SkillInput):
    name: str = Field(max_length=50)


class SkillUpdate(SkillInput):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class SkillDelete(BaseModel):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/api/skills")
def get_skills() -> list[dict]:
    try:
        return [_out(s) for s in load_skills().values()]
    except SkillError as e:
        raise _http_error(e) from None


@router.post("/api/skills", status_code=201)
def create_skill(body: SkillCreate) -> dict:
    # Settings is an explicit owner edit, not a model tool or an imported document.
    try:
        with _LOCK:
            path = save_skill(body.name, body.description, body.instructions, agents=tuple(body.agents))
            result = _out(_read(path.stem, SKILLS_DIR))
    except SkillError as e:
        raise _http_error(e) from None
    audit("setting", "skill_created", detail={"skill": path.stem})
    return result


@router.put("/api/skills/{name}")
def update_skill(name: str, body: SkillUpdate) -> dict:
    try:
        with _LOCK:
            _path(name, SKILLS_DIR)  # updates cannot normalize/rename the target
            save_skill(name, body.description, body.instructions, agents=tuple(body.agents), revision=body.revision)
            result = _out(_read(name, SKILLS_DIR))
    except SkillError as e:
        raise _http_error(e) from None
    audit("setting", "skill_updated", detail={"skill": name})
    return result


@router.delete("/api/skills/{name}", status_code=204)
def remove_skill(name: str, body: SkillDelete) -> Response:
    try:
        delete_skill(name, body.revision)
    except SkillError as e:
        raise _http_error(e) from None
    audit("setting", "skill_deleted", detail={"skill": name})
    return Response(status_code=204)
