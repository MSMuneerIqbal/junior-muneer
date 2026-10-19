"""The path guard (Phase 9): every path a computer tool touches passes here first.

A path is allowed when, after it's made a real full path (".." and links/junctions followed, so they can't lead out):
    - the computer tools are on (Settings → Computer), and
    - it's inside one of your allowed folders, or it (or a folder above it) is written in your own message, and
    - it's not on the blocked list, whatever you say: keys, passwords and secrets, .ssh and similar, AppData (browser
      profiles, saved logins, app tokens), Windows, Program Files, ProgramData, the Recycle Bin and Junior's own data.

A path from an email, a web page or a paste is never "your words": only your own messages count.
"""

import fnmatch
import os
import re
from pathlib import Path

from sqlalchemy import select

from junior.config import get_settings
from junior.db import Message, session_scope
from junior.settings_store import get_setting

DEFAULT_FOLDERS = ("Desktop", "Documents", "Downloads")

# File names that hold secrets, anywhere.
BLOCKED_FILES = (
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.ppk", "*.kdbx", "*.keystore", "*.jks",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", ".netrc", "_netrc", ".git-credentials", ".pypirc", ".npmrc",
    "credentials", "credentials.json", "secret.key", "ntuser.dat*",
)
# Folder names that hold secrets, anywhere in a path.
BLOCKED_DIRS = (".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", "$recycle.bin", "system volume information")
# Folders in your user folder that hold app logins and tokens.
BLOCKED_IN_HOME = ("AppData", ".config", ".local", ".cache", ".claude", ".codex", ".gemini", ".vscode", ".cursor")

WHAT_IS_BLOCKED = [
    "secret files: .env, keys and certificates (.pem, .key, .pfx...), SSH keys, password vaults, saved Git/npm/PyPI logins",
    "secret folders: .ssh, .gnupg, .aws, .azure, .kube, .docker",
    "AppData and app settings in your user folder (browser profiles, saved logins, app tokens)",
    "Windows, Program Files, ProgramData, the Recycle Bin",
    "Junior's own data folder (database, keys, backups)",
]


class PathRefused(Exception):
    """This path can't be used. The message says why, in plain words for the agent to pass on."""


def home() -> Path:
    return Path.home()


def _norm(text: str) -> str:
    """For comparing paths as text: one kind of slash, no case, no trailing slash."""
    return re.sub(r"\\+", "\\\\", text.replace("/", "\\")).casefold().rstrip("\\")


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def expand(text: str) -> Path:
    """The full path for what was written: quotes trimmed, ~ is your user folder, a short path like
    "Desktop\\notes.txt" is inside your user folder. Network and device paths are refused."""
    raw = (text or "").strip().strip('"').strip("'").strip()
    if not raw:
        raise PathRefused("No path given.")
    if raw.startswith(("\\\\", "//")):
        raise PathRefused("Network and device paths (\\\\...) aren't allowed.")
    if raw == "~" or raw.startswith(("~/", "~\\")):
        raw = str(home()) + raw[1:]
    path = Path(raw)
    if not path.is_absolute():
        if path.drive:  # "C:notes.txt": relative to a drive's current folder, too unclear
            raise PathRefused(f"{raw!r} isn't a full path. Use one like C:\\Users\\...\\file.txt.")
        path = home() / path
    return Path(os.path.normpath(path))


def _system_folders() -> list[Path]:
    env = os.environ
    names = [env.get("SystemRoot", r"C:\Windows"), env.get("ProgramFiles", r"C:\Program Files"),
             env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), env.get("ProgramData", r"C:\ProgramData")]
    return [_real(Path(n)) for n in names if n]


def blocked_reason(path: Path) -> str | None:
    """Why a (real, full) path is never allowed, or None."""
    name = path.name.casefold()
    if any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_FILES):
        return f"{path.name} holds secrets (keys, passwords or tokens), so it's never opened."
    parts = {p.casefold() for p in path.parts}
    if hit := next((d for d in BLOCKED_DIRS if d in parts), None):
        return f"Folders named {hit} hold secrets, so they're never opened."
    user = _real(home())
    for folder in BLOCKED_IN_HOME:
        if path.is_relative_to(user / folder):
            return f"{user / folder} holds app logins and tokens, so it's never opened."
    for folder in _system_folders():
        if path.is_relative_to(folder):
            return f"{folder} is a system folder, so it's never touched."
    data = _real(get_settings().data_path)
    if path.is_relative_to(data):
        return "That's Junior's own data folder (database, keys, backups), so it's never touched."
    return None


def default_folders() -> list[Path]:
    """Desktop, Documents and Downloads (OneDrive's copies when Windows keeps them there)."""
    out = []
    for name in DEFAULT_FOLDERS:
        for candidate in (home() / name, home() / "OneDrive" / name):
            if candidate.is_dir():
                out.append(_real(candidate))
                break
    return out


def allowed_folders() -> list[Path]:
    saved = get_setting("computer_folders")
    if saved is None:
        return default_folders()
    return [_real(Path(p)) for p in saved if isinstance(p, str) and p.strip()]


def your_own_paths(context) -> list[str]:
    """Your own messages in this chat (never pasted or outside text), as normalized text to look for paths in."""
    ids = getattr(context, "user_message_ids", None) or []
    if not ids:
        return []
    with session_scope() as s:
        texts = s.scalars(select(Message.content).where(Message.id.in_(ids), Message.source == "user")).all()
    return [_norm(t) for t in texts]


def in_your_words(path: Path, written: Path, context) -> bool:
    """Is this path, or a folder above it, written in one of your own messages? (Never a bare drive like C:\\.)"""
    messages = your_own_paths(context)
    if not messages:
        return False
    for candidate in {path, written, *path.parents, *written.parents}:
        if candidate == Path(candidate.anchor):
            continue
        # The whole path as you wrote it: "...\home\Projects\shop" says nothing about "...\home" itself.
        whole = re.compile(re.escape(_norm(str(candidate))) + r"(?=\\?(?:$|[\s,;:!?)\"'`]|\.(?:$|\s)))")
        if any(whole.search(m) for m in messages):
            return True
    return False


def check(text: str, context=None) -> Path:
    """The real full path for `text`, or PathRefused with the reason."""
    if not get_setting("computer_enabled"):
        raise PathRefused("The computer tools are off. They can turn them on in Settings → Computer.")
    written = expand(text)
    path = _real(written)
    for candidate in (written, path):
        if reason := blocked_reason(candidate):
            raise PathRefused(reason)
    if any(path == folder or path.is_relative_to(folder) for folder in allowed_folders()):
        return path
    if context is not None and in_your_words(path, written, context):
        return path
    folders = ", ".join(str(f) for f in allowed_folders()) or "none yet"
    raise PathRefused(
        f"{path} is outside the allowed folders ({folders}). They can type the full path in their own message to "
        "use it this time, or add the folder in Settings → Computer."
    )


def addable(text: str) -> Path:
    """Check a folder before it's added to your allowed folders."""
    path = _real(expand(text))
    if not path.is_dir():
        raise PathRefused(f"{path} isn't a folder on this PC.")
    if path == Path(path.anchor) and path.anchor.casefold() == _real(home()).anchor.casefold():
        raise PathRefused(f"The whole {path.anchor} drive holds Windows and your programs; pick folders inside it.")
    if path == _real(home()):
        raise PathRefused("Your whole user folder includes AppData and app logins; pick folders inside it.")
    if reason := blocked_reason(path):
        raise PathRefused(reason)
    return path  # a folder with a blocked one inside is fine: the guard still blocks that part
