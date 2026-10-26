"""The app prepares a pinned review; only an owner-approved card can queue the supervisor."""

import asyncio
import os
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from junior.approvals import create_item
from junior.config import get_settings
from junior.permissions import plan_mode_refusal
from junior.senders.base import SendResult
from junior.maintenance.source import MaintenanceError, clean, git, home, read_json, revision, write_json

router = APIRouter()


def folder():
    return get_settings().data_path / "updates"


def supervisor_ready():
    state = read_json(folder() / "supervisor.json", {})
    return bool(os.environ.get("JUNIOR_SUPERVISED") and state.get("session") == os.environ.get("JUNIOR_SUPERVISED")
                and time.time() - state.get("heartbeat", 0) < 15)


def check():
    root = home()
    # A check can preview changes on a dirty tree, but never authorizes overwriting it.
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=all"))
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    remote = git(root, "config", f"branch.{branch}.remote")
    merge = git(root, "config", f"branch.{branch}.merge")
    if not remote or remote.startswith("-") or remote == "." or not merge.startswith("refs/heads/"):
        raise MaintenanceError("Configure a normal Git upstream branch before checking updates.")
    reference = f"refs/junior-check/{uuid.uuid4().hex}"
    git(root, "fetch", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules", remote, f"{merge}:{reference}")
    base = revision(os.environ.get("JUNIOR_REVISION") or git(root, "rev-parse", "HEAD"))
    target = revision(git(root, "rev-parse", reference))
    git(root, "update-ref", "-d", reference)
    try:
        git(root, "merge-base", "--is-ancestor", base, target)
    except MaintenanceError:
        raise MaintenanceError("The configured upstream is behind or diverged from this running revision. Nothing will be downgraded or overwritten.") from None
    changes = git(root, "diff", "--no-ext-diff", "--no-textconv", "--stat", base, target)[:6000]
    result = {"id": uuid.uuid4().hex, "base": base, "target": target,
              "root_head": revision(git(root, "rev-parse", "HEAD")), "changes": changes,
              "dirty": dirty, "supervised": supervisor_ready(), "checked_at": time.time()}
    write_json(folder() / "review.json", result)
    return result


def review_text(review):
    return (f"Update Junior {review['base'][:12]} → {review['target'][:12]}\n\n{review['changes'] or 'No upstream changes.'}\n\n"
            "Install locked dependencies in a separate release; run backend tests, dashboard checks/build and migration rehearsal. "
            "Stop owned servers, back up the database, migrate and restart. Roll back on failed health checks. "
            "Limit: 60 minutes, no retries. Calls/jobs will be interrupted. Junior stays paused after the restart; review the result before resuming.")


def propose(review_id, conversation_id=None):
    if refusal := plan_mode_refusal():
        raise MaintenanceError(refusal)
    review = read_json(folder() / "review.json", {})
    if review.get("id") != review_id or time.time() - review.get("checked_at", 0) > 900:
        raise MaintenanceError("Run a fresh update check first (review expires after 15 minutes).")
    clean(home())
    if review["base"] == review["target"]:
        raise MaintenanceError("Already at this upstream revision.")
    if not supervisor_ready():
        raise MaintenanceError("Start Junior through the supervised start.bat first. No running process will be taken over.")
    item = create_item(kind="api", platform="maintenance", item_type="update", action_type="maintenance.update",
                       title="Review Junior update", text=review_text(review), conversation_id=conversation_id,
                       meta={"review_id": review_id})
    return item


class UpdateSender:
    label = "Junior updates"
    action_types = ("maintenance.update",)

    def is_connected(self):
        return supervisor_ready()

    async def send(self, out):
        try:
            review = read_json(folder() / "review.json", {})
            if out.meta.get("review_id") != review.get("id") or out.text != review_text(review):
                raise MaintenanceError("The reviewed update changed. Prepare a new card.")
            if time.time() - review["checked_at"] > 900 or not supervisor_ready():
                raise MaintenanceError("The update review/supervisor expired. Check again.")
            await asyncio.to_thread(clean, home())
            if git(home(), "rev-parse", "HEAD") != review["root_head"]:
                raise MaintenanceError("The source revision changed. Check again.")
            if read_json(folder() / "request.json"):
                raise MaintenanceError("An update is already queued. Check its progress.")
            request = {**review, "conversation_id": out.meta.get("conversation_id"), "approval_id": out.item_id,
                       "queued_at": time.time(), "session": os.environ["JUNIOR_SUPERVISED"]}
            write_json(folder() / "request.json", request)
            return SendResult("sent", "Update queued for the supervisor. Progress is in Settings → Advanced. Junior will pause before restart.")
        except (MaintenanceError, OSError, KeyError):
            return SendResult("failed", "Update was not queued. Check the current review, clean source and supervised launcher; prepare a new card.")


@router.get("/api/updates")
def status():
    report()
    return {"supervised": supervisor_ready(), "review": read_json(folder() / "review.json"),
            "progress": read_json(folder() / "progress.json")}


def report():
    """Save a terminal result once to an existing originating chat; never recreate a deleted session."""
    from junior.db import ApprovalItem, Conversation, Message, Setting, session_scope
    from sqlalchemy.exc import IntegrityError
    state = read_json(folder() / "progress.json", {})
    if state.get("state") not in {"done", "failed", "rolled_back", "interrupted"} or not state.get("approval_id"):
        return
    try:
        with session_scope() as session:
            approval = session.get(ApprovalItem, state["approval_id"])
            conversation_id = approval.conversation_id if approval else None
            marker = f"update_report_{state['approval_id']}"
            if not conversation_id or not session.get(Conversation, conversation_id) or session.get(Setting, marker):
                return
            text = f"Update #{state['approval_id']}: {state['step']}"
            session.add(Setting(key=marker, value=True))
            session.add(Message(conversation_id=conversation_id, role="assistant", source="assistant", content=text))
    except IntegrityError:
        pass  # A concurrent poll committed the same report; the whole losing transaction is rolled back.


class MaintenanceGuard:
    """Pause requests during the database/release switch so rollback cannot lose new writes."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if os.environ.get("JUNIOR_SUPERVISED") and scope["type"] in {"http", "websocket"} and scope.get("path") != "/health":
            state = read_json(folder() / "progress.json", {})
            if state.get("state") in {"switching", "rolling_back"}:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1013})
                else:
                    from starlette.responses import JSONResponse
                    await JSONResponse({"detail": "Junior is switching releases. Reconnect shortly."}, status_code=503)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@router.post("/api/updates/check")
async def api_check():
    try:
        return await asyncio.to_thread(check)
    except (MaintenanceError, OSError) as error:
        raise HTTPException(409, str(error) if isinstance(error, MaintenanceError) else "Could not check updates.") from None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str


@router.post("/api/updates/propose")
def api_propose(body: Review):
    try:
        return propose(body.review_id)
    except (MaintenanceError, OSError) as error:
        raise HTTPException(409, str(error) if isinstance(error, MaintenanceError) else "Could not prepare an update.") from None
