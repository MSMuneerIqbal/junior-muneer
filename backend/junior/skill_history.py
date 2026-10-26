"""Archive complete skill bundles before changes/deletion; current content remains one atomic Markdown file.

Resources are text bundled in the validated YAML header, loaded individually. They are never paths to execute.
Version history is bounded, private app state, not prompts or a source of personal memory.
"""

import re
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from junior.config import get_settings

router = APIRouter()
REVISION = re.compile(r"^[a-f0-9]{64}$")


def _directory(name, *, create=False):
    from junior import skills
    skills._path(name, skills.SKILLS_DIR)
    root = get_settings().data_path / "skill_history"
    folder = root / name
    for path in (root, folder):
        if path.is_symlink() or path.is_junction():
            raise skills.SkillError("Skill history cannot use linked folders.")
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def archive(name, text, modified_at=None):
    from junior import skills
    parsed = skills.parse_skill(text, f"{name}.md")
    folder = _directory(name, create=True)
    path = folder / f"{parsed.revision}.md"
    if path.is_symlink():
        raise skills.SkillError("Skill history cannot use linked files.")
    if path.exists() and (path.stat().st_size > skills.MAX_SKILL_BYTES or skills.parse_skill(path.read_text(encoding="utf-8"), f"{name}.md").revision != parsed.revision):
        raise skills.SkillError("The existing history archive is damaged; the active skill was not changed.")
    if not path.exists():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=folder, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    os.utime(path, (modified_at, modified_at) if modified_at is not None else None)
    files = sorted((p for p in folder.glob("*.md") if REVISION.fullmatch(p.stem) and not p.is_symlink()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[20:]:
        old.unlink()  # only our immutable SHA-256 history files


def versions(name):
    from junior import skills
    folder = _directory(name)
    result = []
    current = None
    try:
        current = skills._read(name, skills.SKILLS_DIR)
        path = skills._path(name, skills.SKILLS_DIR)
        result.append({"revision": current.revision, "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(), "current": True})
    except skills.SkillNotFound:
        pass
    for path in sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not REVISION.fullmatch(path.stem) or path.is_symlink() or current and path.stem == current.revision:
            continue
        result.append({"revision": path.stem, "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(), "current": False})
    return result[:21]


def version(name, revision):
    from junior import skills
    if not REVISION.fullmatch(revision):
        raise skills.SkillNotFound("Choose a saved skill version.")
    try:
        current = skills._read(name, skills.SKILLS_DIR)
        if current.revision == revision:
            return skills._out(current)
    except skills.SkillNotFound:
        pass
    path = _directory(name) / f"{revision}.md"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > skills.MAX_SKILL_BYTES:
        raise skills.SkillNotFound("That skill version is unavailable.")
    parsed = skills.parse_skill(path.read_text(encoding="utf-8"), f"{name}.md")
    if parsed.revision != revision:
        raise skills.SkillError("That skill version is damaged; it was not loaded.")
    return skills._out(parsed)


@router.get("/api/skills-deleted")
def deleted():
    from junior import skills
    root = get_settings().data_path / "skill_history"
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        return []
    result = []
    with skills._LOCK:
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
                continue
            try:
                if not skills._path(folder.name, skills.SKILLS_DIR).exists() and (saved := versions(folder.name)):
                    result.append({"name": folder.name, "revision": saved[0]["revision"], "modified_at": saved[0]["modified_at"]})
            except skills.SkillError:
                continue
    return result


@router.get("/api/skills/{name}/versions")
def get_versions(name: str):
    from junior import skills
    try:
        with skills._LOCK:
            return versions(name)
    except (skills.SkillError, OSError):
        raise HTTPException(422, "Could not read that skill's history.") from None


@router.get("/api/skills/{name}/versions/{revision}")
def get_version(name: str, revision: str):
    from junior import skills
    try:
        with skills._LOCK:
            return version(name, revision)
    except skills.SkillError as error:
        raise skills._http_error(error) from None
    except OSError:
        raise HTTPException(422, "Could not read that skill version.") from None
