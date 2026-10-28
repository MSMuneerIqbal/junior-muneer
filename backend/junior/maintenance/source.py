"""Bounded, noninteractive Git reads and safe tracked-source export (no checkout hooks)."""

import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_SOURCE = 32 * 1024 * 1024


class MaintenanceError(Exception):
    pass


def home():
    return Path(os.environ.get("JUNIOR_HOME") or Path(__file__).resolve().parents[3]).resolve()


def git(root, *args, binary=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_PAGER": "cat"}
    # No hooks, fsmonitor commands, external diff/textconv, or custom Git protocols.
    try:
        result = subprocess.run(["git", "-c", "core.hooksPath=NUL", "-c", "core.fsmonitor=false",
                                 "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never",
                                 "-C", str(root), *args], env=env, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise MaintenanceError("Git did not finish in 30 seconds. Nothing was applied.") from None
    if result.returncode:
        raise MaintenanceError("Git could not complete this check. Check the configured upstream and your Git login locally.")
    if len(result.stdout) > MAX_SOURCE:
        raise MaintenanceError("Source/check output exceeds the 32 MB limit.")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace").strip()


def clean(root):
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise MaintenanceError("Local edits or untracked files exist. Save/commit them yourself before updating; Junior will not stash or discard them.")


def revision(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise MaintenanceError("Expected an exact Git revision.")
    return value


def safe_path(name):
    path = PurePosixPath(name)
    forbidden = {".git", ".venv", "node_modules", ".ssh", ".next", ".next-e2e", "__pycache__"}
    devices = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if (not name or "\\" in name or ":" in name or path.is_absolute() or path.as_posix() != name.rstrip("/") or
            tuple(p.casefold() for p in path.parts[:1]) == ("data",) or
            tuple(p.casefold() for p in path.parts[:2]) == ("backend", "data") or
            any(p.rstrip(" .") != p or p.split(".")[0].casefold() in devices for p in path.parts) or
            any(p in {"", ".", ".."} or p.casefold() in forbidden or
                (p.casefold().startswith(".env") and p != ".env.example") or
                p.casefold().endswith((".pem", ".key", ".pfx", ".db")) for p in path.parts)):
        raise MaintenanceError("Source contains a private or unsafe path.")
    return path


def export(root, sha, destination):
    """Only regular tracked files, at most 32 MB expanded, 5,000 entries. Never extract links."""
    revision(sha)
    archive = git(root, "archive", "--format=tar", sha, binary=True)
    destination = Path(destination)
    if destination.exists():
        raise MaintenanceError("This staging directory already exists; it will not be overwritten.")
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        if len(members) > 5000 or sum(m.size for m in members) > MAX_SOURCE:
            raise MaintenanceError("Tracked source exceeds the staging limit.")
        seen = set()
        for member in members:
            safe_path(member.name)
            if not (member.isfile() or member.isdir()) or member.name.casefold() in seen:
                raise MaintenanceError("Source links, special files and duplicate paths cannot be staged.")
            seen.add(member.name.casefold())
        destination.mkdir(parents=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink() or path.parent.is_junction():
        raise MaintenanceError("Maintenance storage cannot be a link.")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        # Windows readers and security scanners can briefly hold the destination
        # without delete sharing. Keep atomic replacement, but tolerate that race.
        for attempt in range(10):
            try:
                temp.replace(path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 9:
                    raise
                time.sleep(.05)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    if path.is_symlink() or path.stat().st_size > 1_000_000:
        raise MaintenanceError("Invalid maintenance record.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MaintenanceError("Could not read the maintenance record.") from None
