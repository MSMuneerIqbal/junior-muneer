"""The Computer sender (Phase 9): plain code, never AI, that carries out one approved computer action on this PC.

Like every sender it runs only after the Safety Guard and "run at most once" (senders/dispatch.py). The path was
checked when the card was made; it's checked again here (paths.recheck), right before anything changes.
A file that gets replaced goes to the Recycle Bin first, so every change can be undone.
"""

import logging
import os
import tempfile
from pathlib import Path

from junior.computer.paths import PathRefused, recheck
from junior.senders.base import Outgoing, SendResult
from junior.settings_store import get_setting

log = logging.getLogger(__name__)

ACTIONS = ("computer.write", "computer.move", "computer.delete", "computer.run")


def to_recycle_bin(path: Path) -> None:
    from send2trash import send2trash

    send2trash(str(path))


def write_text(path: Path, text: str) -> None:
    """Write the whole file at once (a temporary file, then swapped in), so a half-written file never stays."""
    fd, temp = tempfile.mkstemp(prefix=".junior-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


class ComputerSender:
    label = "Your PC"
    action_types = ACTIONS

    def is_connected(self) -> bool:
        return bool(get_setting("computer_enabled"))

    async def send(self, out: Outgoing) -> SendResult:
        op = out.meta.get("op", "")
        try:
            path = recheck(out.meta.get("path", ""))
            if op == "write":
                return self._write(path, out.text, bool(out.meta.get("replace")), out.meta.get("old_sha", ""))
            if op == "mkdir":
                return self._mkdir(path)
            if op == "move":
                return self._move(path, recheck(out.meta.get("to", "")))
            if op == "delete":
                return self._delete(path)
            if op == "run":
                return await self._run(path, out.text, float(out.meta.get("seconds") or 120))
        except PathRefused as e:
            return SendResult("failed", str(e))
        except OSError as e:  # nothing (or only the Recycle Bin copy) happened: safe to try again by hand
            return SendResult("failed", f"Windows refused it: {e.strerror or e}")
        return SendResult("failed", f"Unknown computer action {op!r}; nothing was done.")

    @staticmethod
    def _write(path: Path, text: str, replace: bool, old_sha: str = "") -> SendResult:
        if not path.parent.is_dir():
            return SendResult("failed", f"The folder {path.parent} doesn't exist; nothing was written.")
        if path.is_dir():
            return SendResult("failed", f"{path} is a folder; nothing was written.")
        existed = path.exists()
        if existed and not replace:
            return SendResult("failed", f"{path.name} appeared there since the card was made; nothing was written.")
        if existed:
            from junior.computer.tools import fingerprint

            if old_sha and fingerprint(path) != old_sha:
                return SendResult("failed", f"{path.name} changed since the card was made; nothing was written. Ask for the change again.")
            to_recycle_bin(path)  # the old version, for undo
        write_text(path, text)
        how = "Replaced (the old version is in the Recycle Bin)" if existed else "Created"
        return SendResult("sent", f"{how}: {path} ({len(text.encode('utf-8')):,} bytes).")

    @staticmethod
    def _mkdir(path: Path) -> SendResult:
        if path.exists():
            return SendResult("sent" if path.is_dir() else "failed",
                              f"{path} already exists." if path.is_dir() else f"{path} is a file, not a folder.")
        path.mkdir(parents=True)
        return SendResult("sent", f"Made the folder {path}.")

    @staticmethod
    def _move(src: Path, dest: Path) -> SendResult:
        import shutil

        if not src.exists():
            return SendResult("failed", f"{src} isn't there any more; nothing was moved.")
        if dest.exists():
            return SendResult("failed", f"{dest} exists now; nothing was moved.")
        if not dest.parent.is_dir():
            return SendResult("failed", f"The folder {dest.parent} doesn't exist; nothing was moved.")
        shutil.move(str(src), str(dest))
        return SendResult("sent", f"Moved {src} to {dest}.")

    @staticmethod
    def _delete(path: Path) -> SendResult:
        from junior.computer.tools import _is_allowed_root

        if not path.exists():
            return SendResult("sent", f"{path} was already gone.")
        if _is_allowed_root(path):
            return SendResult("failed", f"{path} is one of your allowed folders; it isn't deleted.")
        to_recycle_bin(path)
        return SendResult("sent", f"{path} is in the Recycle Bin (restore it from there if you need it).")

    @staticmethod
    async def _run(folder: Path, command: str, seconds: float) -> SendResult:
        from junior.computer.terminal import refusal, run_powershell

        if why := refusal(command):  # the card's command may have been edited
            return SendResult("failed", f"That command is never run here ({why}).")
        if not folder.is_dir():
            return SendResult("failed", f"The folder {folder} isn't there any more; nothing ran.")
        ran = await run_powershell(command, str(folder), seconds)
        if ran.code is None:
            head = f"Stopped after {seconds:.0f} seconds (the time limit)."
        else:
            head = "Finished (exit code 0)." if ran.code == 0 else f"Finished with an error (exit code {ran.code})."
        return SendResult("sent", f"{head}\n{ran.output or '(no output)'}")
