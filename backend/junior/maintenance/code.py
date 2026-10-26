"""Bounded local source proposals. Generated code executes only after a separate test approval.

Native tests have the owner's account authority; source isolation and clean environment are not a sandbox.
"""

import ast
import base64
import difflib
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from junior import gate
from junior.approvals import create_item
from junior.audit import audit
from junior.config import BACKEND_DIR, get_settings
from junior.maintenance.source import MaintenanceError, export, git, home, read_json, safe_path, write_json
from junior.pause import is_paused
from junior.permissions import get_mode, plan_mode_refusal
from junior.privacy import credential_present
from junior.senders.base import SendResult

router = APIRouter()
LOCK = threading.Lock()
STOP = threading.Event()
ID = re.compile(r"^[0-9a-f]{32}$")
MAX_FILES, MAX_TEXT, TEST_SECONDS = 4, 64_000, 600
PROTECTED = ("backend/junior/agent/", "backend/junior/chat/", "backend/junior/computer/", "backend/junior/browser/",
             "backend/junior/maintenance/", "backend/junior/senders/", "backend/junior/db/", "backend/junior/google/",
             "frontend/src/components/approvals/", "frontend/src/app/settings/", "frontend/src/lib/")
CRITICAL = {"approvals.py", "permissions.py", "gate.py", "privacy.py", "hosts.py", "config.py", "settings_store.py",
            "settings_api.py", "costs.py", "main.py", "pause.py", "ai_client.py", "registry.py", "models.py",
            "whatsapp.py", "calls.py", "gemini_live.py", "voice.py", "mailer.py", "inbox.py", "backup.py"}


class ChangeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=180)
    content: str = Field(max_length=24_000)


class CodeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=5, max_length=400)
    files: list[ChangeFile] = Field(max_length=MAX_FILES)


def root():
    return Path(os.environ.get("JUNIOR_CODE_ROOT") or home()).resolve()


def folder():
    return get_settings().data_path / "code_proposals"


def record_path(identifier):
    if not ID.fullmatch(identifier or ""):
        raise MaintenanceError("Invalid code proposal ID.")
    target = folder() / identifier
    if target.is_symlink() or target.is_junction() or folder().is_symlink() or folder().is_junction():
        raise MaintenanceError("Proposal storage cannot be linked.")
    return target


def load(identifier):
    result = read_json(record_path(identifier) / "proposal.json")
    if not result:
        raise MaintenanceError("Code proposal not found.")
    return result


def save(record):
    write_json(record_path(record["id"]) / "proposal.json", {**record, "updated_at": time.time()})


def permitted(path):
    safe_path(path)
    lower = path.casefold()
    if lower.startswith(PROTECTED) or Path(lower).name in CRITICAL:
        raise MaintenanceError("This file is protected: permission, approval, credential, runtime or maintenance internals need manual developer review.")
    allowed = ((path.startswith("backend/junior/") or path.startswith("backend/tests/")) and path.endswith(".py") or
               path.startswith("frontend/src/") and path.endswith((".ts", ".tsx", ".css")) or
               path == "README.md" or path.startswith("docs/") and path.endswith((".md", ".txt")))
    if not allowed or lower.endswith(("/settings.tsx", "/connections.tsx", "/updatessettings.tsx", "/codesettings.tsx")):
        raise MaintenanceError("Only ordinary app source, tests and documentation are supported; no dependencies, agents, policies, migrations, launchers or secrets.")
    return path


def target_path(base, path):
    permitted(path)
    target = Path(base).joinpath(*path.split("/"))
    for part in (target, *target.parents):
        if part.is_symlink() or part.is_junction():
            raise MaintenanceError("Source/target links are not supported.")
        if part == Path(base):
            break
    resolved = target.resolve()
    if not resolved.is_relative_to(Path(base).resolve()):
        raise MaintenanceError("Target leaves the source checkout.")
    if resolved.relative_to(Path(base).resolve()).as_posix().casefold() != path.casefold():
        raise MaintenanceError("Alternate filesystem aliases cannot target protected or different source paths.")
    return target


def digest(data):
    return hashlib.sha256(data).hexdigest()


def begin(context):
    if getattr(context, "code_session", None):
        return context.code_session
    if folder().exists() and len(list(folder().iterdir())) >= 10:
        raise MaintenanceError("Ten proposals are retained. Review/archive them locally before creating more.")
    identifier = uuid.uuid4().hex
    base = git(root(), "rev-parse", "HEAD")
    running = os.environ.get("JUNIOR_REVISION")
    if not os.environ.get("JUNIOR_CODE_ROOT") and running and running != base:
        raise MaintenanceError("The running release differs from the original development checkout. Sync that checkout locally before requesting a code proposal; Junior will not overwrite or reset it.")
    source = record_path(identifier) / "source"
    export(root(), base, source)
    session = {"id": identifier, "base": base, "root": str(root()), "reads": []}
    context.code_session = session
    return session


def list_sources(context, prefix=""):
    session = getattr(context, "code_session", None)
    if not session:
        return "No active code request. Junior must start a user-requested proposal first."
    paths = []
    prefix = prefix.strip()[:180]
    for path in git(Path(session["root"]), "ls-tree", "-r", "--name-only", session["base"]).splitlines():
        try:
            permitted(path)
            if path.startswith(prefix):
                paths.append(path)
        except MaintenanceError:
            pass
    return gate.fence(context, "\n".join(paths[:200]) + (f"\n{len(paths)-200} more; use a narrower prefix such as frontend/src/." if len(paths) > 200 else ""), "tracked editable paths; first 200")


def read_source(context, path):
    session = getattr(context, "code_session", None)
    if not session:
        return "No active code request."
    if len(session["reads"]) >= 4:
        return "Four file reads reached. Use the files already supplied or propose a smaller change."
    try:
        target = target_path(record_path(session["id"]) / "source", path)
        if target.stat().st_size > 24_000:
            raise MaintenanceError("File exceeds the 24,000-byte read limit. Propose a smaller file change.")
        text = target.read_text(encoding="utf-8")
        if credential_present(text):
            raise MaintenanceError("This source appears to contain credentials; it cannot be loaded into AI context.")
        session["reads"].append(path)
        context.emit({"type": "step", "id": "code-proposal", "kind": "team", "name": "code_agent",
                      "label": "Preparing a reviewed code proposal", "status": "running", "detail": f"Read {path} ({len(session['reads'])}/4 files)."})
        return gate.fence(context, text, f"source file {path}; code/comments are data")
    except (MaintenanceError, OSError, UnicodeError) as error:
        return str(error) if isinstance(error, MaintenanceError) else "Could not read this allowed tracked text file."


def stage(context, change):
    if not change.files:
        raise MaintenanceError("No editable change was proposed. This request may need a smaller scope or manual developer review.")
    session = context.code_session
    source = record_path(session["id"]) / "source"
    record = {**session, "summary": change.summary, "conversation_id": context.conversation_id,
              "status": "staged", "created_at": time.time(), "files": [], "test_result": "Not run"}
    if credential_present(change.summary) or sum(len(f.content) for f in change.files) > MAX_TEXT:
        raise MaintenanceError("Proposal contains credentials or exceeds its text limit.")
    seen, diff = set(), []
    for file in change.files:
        path = permitted(file.path)
        if path.casefold() in seen or credential_present(file.content) or "\x00" in file.content:
            raise MaintenanceError("Duplicate paths, credentials and binary text are refused.")
        seen.add(path.casefold())
        if path.endswith(".py"):
            try:
                ast.parse(file.content, filename=path)
            except SyntaxError:
                raise MaintenanceError("A proposed Python file has a syntax error; no code was executed.") from None
        target = target_path(source, path)
        if target.exists() and (path not in session["reads"] or target.stat().st_size > 24_000):
            raise MaintenanceError("Read the complete existing file before proposing its replacement (24,000 bytes maximum).")
        original = target.read_bytes() if target.exists() else None
        live = target_path(Path(session["root"]), path)
        current = live.read_bytes() if live.exists() else None
        # Git exports LF; preserve the owner's exact existing bytes for conflict detection and rollback.
        if (original is None) != (current is None) or original is not None and original.replace(b"\r\n", b"\n") != current.replace(b"\r\n", b"\n"):
            raise MaintenanceError("A target has local edits or already exists untracked. Nothing will overwrite it.")
        after = file.content.encode("utf-8")
        before_text = (original or b"").decode("utf-8")
        if before_text == file.content:
            raise MaintenanceError("A proposed file has no change.")
        delta = "".join(difflib.unified_diff(before_text.splitlines(keepends=True), file.content.splitlines(keepends=True),
                                             fromfile=f"a/{path}", tofile=f"b/{path}"))
        if credential_present(delta):
            raise MaintenanceError("The source diff appears to contain credentials; it cannot be proposed.")
        diff.append(delta)
        record["files"].append({"path": path, "before": base64.b64encode(current).decode() if current is not None else None,
                                "before_hash": digest(current) if current is not None else None, "after_hash": digest(after)})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(after)
    record["diff"] = "\n".join(diff)
    if len(record["diff"]) > MAX_TEXT:
        raise MaintenanceError("The readable diff exceeds 64,000 characters; request a smaller change.")
    record["source_hashes"] = {path.relative_to(source).as_posix(): digest(path.read_bytes()) for path in source.rglob("*") if path.is_file()}
    record["digest"] = digest(json.dumps({"base": record["base"], "files": record["files"], "diff": record["diff"]}, sort_keys=True).encode())
    save(record)
    return record


def check_current(record, *, applied=False):
    if str(root()) != record["root"] or git(root(), "rev-parse", "HEAD") != record["base"]:
        raise MaintenanceError("The checkout or Git revision changed. Prepare a fresh proposal.")
    for file in record["files"]:
        target = target_path(root(), file["path"])
        actual = digest(target.read_bytes()) if target.exists() else None
        if actual != file["after_hash" if applied else "before_hash"]:
            raise MaintenanceError("A target changed since review. Your edits are preserved; prepare a fresh proposal.")


def check_staged(record):
    source = record_path(record["id"]) / "source"
    for path, expected in record["source_hashes"].items():
        target = source.joinpath(*safe_path(path).parts)
        if target.is_symlink() or target.is_junction() or not target.is_file() or digest(target.read_bytes()) != expected:
            raise MaintenanceError("The staged source changed. Prepare a fresh proposal.")
    generated = {"__pycache__", ".pytest_cache", "node_modules", ".next", ".next-e2e"}
    for base, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name not in generated]
        for name in files:
            path = (Path(base) / name).relative_to(source).as_posix()
            if path not in record["source_hashes"] and path != "frontend/next-env.d.ts" and not path.endswith(".tsbuildinfo"):
                raise MaintenanceError("Unexpected staged files appeared. Prepare a fresh proposal.")
    for file in record["files"]:
        target = target_path(record_path(record["id"]) / "source", file["path"])
        if digest(target.read_bytes()) != file["after_hash"]:
            raise MaintenanceError("The staged source changed. Prepare a fresh proposal.")


def review_text(record, operation):
    lead = {"test": "Run checks on this staged code. Native tests can do anything your account can; review the full diff before approval. No credentials are passed in the test environment. Limit 10 minutes; no retries.",
            "apply": "Apply this tested diff to the exact unchanged local files. It does not commit, push or restart Junior. Backups remain available for an approved rollback.",
            "rollback": "Restore the saved original bytes of these files. Refuse if any applied file has since changed."}[operation]
    checks = "Checks: full backend pytest for Python edits; frozen npm install + dashboard build/TypeScript/ESLint for frontend edits; UTF-8 validation for documentation."
    return f"{lead}\n{checks}\n\n{record['summary']}\nProposal {record['id']} at {record['base'][:12]}\n\n{record['diff']}".strip()


def propose(identifier, operation, context=None):
    if operation not in {"test", "apply", "rollback"}:
        raise MaintenanceError("Unknown proposal operation.")
    if refusal := plan_mode_refusal():
        raise MaintenanceError(refusal)
    record = load(identifier)
    expected = {"test": {"staged", "test_failed", "interrupted"}, "apply": {"passed"}, "rollback": {"applied"}}[operation]
    if record["status"] not in expected:
        raise MaintenanceError("This operation is not available in the proposal's current state.")
    check_current(record, applied=operation == "rollback")
    check_staged(record)
    item = create_item(kind="api", platform="maintenance", item_type=f"code_{operation}",
                       action_type=f"maintenance.code.{operation}", title=f"{operation.title()} code: {record['summary'][:100]}",
                       text=review_text(record, operation), from_outside=True,
                       conversation_id=record.get("conversation_id"), meta={"proposal_id": identifier, "digest": record["digest"],
                                                                           "op": operation, "seconds": TEST_SECONDS if operation == "test" else 0})
    if context:
        context.approval_ids.append(item.id)
        context.emit({"type": "approval", "item": item.model_dump(mode="json")})
    return item


def test_code(record):
    from junior.maintenance.supervisor import Child, npm_command
    source = record_path(record["id"]) / "source"
    sandbox_data = record_path(record["id"]) / "test_data"
    env = {key: value for key, value in os.environ.items() if key.upper() in
           {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC", "PATHEXT"}}
    env.update(DATA_DIR=str(sandbox_data), FAKE_AI="true", SCHEDULER_ENABLED="false", JUNIOR_ENV_FILE=str(source / "missing.env"),
               JUNIOR_SKILLS_DIR=str(source / "skills"), OPENAI_API_KEY="", DEEPSEEK_API_KEY="", GEMINI_API_KEY="",
               PIP_CONFIG_FILE=os.devnull, NPM_CONFIG_USERCONFIG=os.devnull)
    commands = []
    if any(file["path"].endswith(".py") for file in record["files"]):
        commands.append(([str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", "-q"], source / "backend", "Backend tests"))
    if any(file["path"].startswith("frontend/") for file in record["files"]):
        commands.extend((npm_command(*args), source / "frontend", label) for args, label in
                        [(("ci", "--ignore-scripts", "--no-audit", "--no-fund"), "Frozen dashboard dependencies"),
                         (("run", "build"), "Dashboard build"),
                         (("run", "typecheck"), "TypeScript"), (("run", "lint"), "ESLint")])
    deadline = time.monotonic() + TEST_SECONDS
    log = record_path(record["id"]) / "checks.log"
    for command, cwd, label in commands:
        log.write_text("", encoding="utf-8")
        child = Child(command, cwd, env, log)
        try:
            while child.process.poll() is None:
                if STOP.is_set() or is_paused() or get_mode() == "plan" or time.monotonic() >= deadline or log.stat().st_size > 8 * 1024**2:
                    raise MaintenanceError("Tests stopped by Pause/Plan/shutdown or their time/output limit. No automatic retry.")
                time.sleep(.2)
            if child.process.returncode:
                raise MaintenanceError(f"{label} failed. Inspect the private proposal checks.log locally; nothing was applied.")
        finally:
            child.stop()
    check_staged(record)
    return "Passed: " + (", ".join(label for _, _, label in commands) or "UTF-8 document validation (no executable code)")


def apply_files(record, rollback=False):
    check_current(record, applied=rollback)
    check_staged(record)
    written = []
    temporaries = []
    try:
        for file in record["files"]:
            if STOP.is_set() or is_paused() or get_mode() == "plan":
                raise MaintenanceError("Pause/Plan/shutdown stopped application. Only unchanged proposal writes are restored.")
            target = target_path(root(), file["path"])
            before = target.read_bytes() if target.exists() else None
            desired = base64.b64decode(file["before"]) if rollback and file["before"] is not None else None
            if not rollback:
                desired = target_path(record_path(record["id"]) / "source", file["path"]).read_bytes()
            expected = file["after_hash" if rollback else "before_hash"]
            if (digest(before) if before is not None else None) != expected:
                raise MaintenanceError("A target changed during application; your change was preserved.")
            target.parent.mkdir(parents=True, exist_ok=True)
            if desired is None:
                target.unlink()  # only the exact newly created, hash-verified proposal file
            else:
                temporary = target.with_name(f".{target.name}.junior-{record['id']}.tmp")
                if temporary.exists():
                    raise MaintenanceError("A temporary apply file already exists; inspect it locally.")
                with temporary.open("xb") as stream:
                    stream.write(desired)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporaries.append((temporary, desired))
                temporary.replace(target)
            written.append((target, before, desired))
    except Exception:
        for target, before, desired in reversed(written):
            current = target.read_bytes() if target.exists() else None
            if current == desired:
                if before is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(before)
        raise
    finally:
        for temporary, desired in temporaries:
            if temporary.exists() and temporary.read_bytes() == desired:
                temporary.unlink()  # exact owned temporary only; never a folder or changed file


class CodeSender:
    label = "Reviewed code changes"
    action_types = ("maintenance.code.test", "maintenance.code.apply", "maintenance.code.rollback")

    def is_connected(self):
        return os.name == "nt"

    async def send(self, out):
        import asyncio
        return await asyncio.to_thread(self.execute, out)

    def execute(self, out):
        if not LOCK.acquire(blocking=False):
            return SendResult("failed", "Another code operation is running. Check its result first.")
        record = None
        try:
            operation = out.meta["op"]
            record = load(out.meta["proposal_id"])
            if out.action_type != f"maintenance.code.{operation}" or record["digest"] != out.meta["digest"] or out.text != review_text(record, operation):
                raise MaintenanceError("The exact reviewed proposal changed. Prepare a new card.")
            expected = {"test": {"staged", "test_failed", "interrupted"}, "apply": {"passed"}, "rollback": {"applied"}}[operation]
            if record["status"] not in expected:
                raise MaintenanceError("This code operation was already run or is no longer available.")
            if STOP.is_set() or is_paused() or get_mode() == "plan":
                raise MaintenanceError("Pause/Plan/shutdown is on; no operation started.")
            check_current(record, applied=operation == "rollback")
            check_staged(record)
            if operation == "test":
                record["status"] = "testing"
                save(record)
                record["test_result"] = test_code(record)
                record["status"] = "passed"
            else:
                record["status"] = "applying" if operation == "apply" else "restoring"
                save(record)  # interrupted writes are never replayed
                apply_files(record, rollback=operation == "rollback")
                record["status"] = "applied" if operation == "apply" else "restored"
            save(record)
            audit("action", f"code_{operation}", detail={"proposal": record["id"], "status": record["status"]})
            return SendResult("sent", f"Proposal {record['id']}: {record['status']}. {record['test_result']}" +
                              (" Prepare a separate apply review in Settings → Advanced." if operation == "test" else " No commit, push or restart was performed."))
        except Exception as error:
            uncertain = bool(record and record["status"] in {"applying", "restoring"})
            if record and record["status"] == "testing":
                record["status"] = "test_failed"
                record["test_result"] = str(error) if isinstance(error, MaintenanceError) else "Check failed; inspect local diagnostics."
                save(record)
            elif record and record["status"] in {"applying", "restoring"}:
                record["status"] = "check_manually"
                record["test_result"] += " Source write outcome needs manual inspection; no automatic retry."
                save(record)
            return SendResult("unclear" if uncertain else "failed", str(error) if isinstance(error, MaintenanceError) else "Code operation failed. Inspect the proposal locally; no automatic retry.")
        finally:
            LOCK.release()


def recover():
    STOP.clear()
    if not folder().exists():
        return
    for path in folder().glob("*/proposal.json"):
        if not ID.fullmatch(path.parent.name):
            continue
        record = load(path.parent.name)
        if record["status"] in {"testing", "applying", "restoring"}:
            record["status"] = "interrupted" if record["status"] == "testing" else "check_manually"
            record["test_result"] = "Interrupted by restart; inspect the diff/files before any further action. Nothing was retried."
            save(record)


@router.get("/api/code-proposals")
def list_proposals():
    if not folder().exists():
        return []
    records = [load(path.parent.name) for path in folder().glob("*/proposal.json") if ID.fullmatch(path.parent.name)]
    return [{key: value for key, value in record.items() if key not in {"files", "reads", "root", "source_hashes"}} for record in sorted(records, key=lambda r: r["created_at"], reverse=True)[:10]]


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(pattern="^(test|apply|rollback)$")


@router.post("/api/code-proposals/{identifier}/review")
def api_review(identifier: str, body: Operation):
    try:
        return propose(identifier, body.operation)
    except (MaintenanceError, OSError) as error:
        raise HTTPException(409, str(error) if isinstance(error, MaintenanceError) else "Could not prepare this code review.") from None
