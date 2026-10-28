"""Settings → Computer.

    GET  /api/computer                    on/off, your allowed folders, what's always blocked
    POST /api/computer/folders  {"path"}  allow a folder (checked: it exists, isn't blocked, isn't a whole drive)
    POST /api/computer/folders/remove  {"path"}
On/off is the `computer_enabled` setting (PATCH /api/settings).
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from junior.audit import audit
from junior.computer.paths import WHAT_IS_BLOCKED, PathRefused, addable, allowed_folders, default_folders
from junior.settings_store import get_setting, set_setting

router = APIRouter()


class FolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=500)


def status() -> dict:
    return {
        "enabled": bool(get_setting("computer_enabled")),
        "all_files": bool(get_setting("computer_all_files")),
        "folders": [{"path": str(f), "exists": f.is_dir()} for f in allowed_folders()],
        "using_defaults": get_setting("computer_folders") is None,
        "defaults": [str(f) for f in default_folders()],
        "blocked": WHAT_IS_BLOCKED,
    }


@router.get("/api/computer")
def get_computer() -> dict:
    return status()


@router.post("/api/computer/folders")
def add_folder(body: FolderBody) -> dict:
    try:
        path = addable(body.path)
    except PathRefused as e:
        raise HTTPException(400, str(e)) from None
    folders = allowed_folders()
    if not any(path == f for f in folders):
        set_setting("computer_folders", [str(f) for f in folders] + [str(path)])
        audit("setting", "computer_folder_added", detail={"path": str(path)})
    return status()


@router.post("/api/computer/folders/remove")
def remove_folder(body: FolderBody) -> dict:
    target = Path(body.path)
    folders = allowed_folders()
    kept = [f for f in folders if f != target]
    if len(kept) == len(folders):
        raise HTTPException(404, "That folder isn't in the list.")
    set_setting("computer_folders", [str(f) for f in kept])
    audit("setting", "computer_folder_removed", detail={"path": body.path})
    return status()


@router.get("/api/computer/jobs")
def computer_jobs() -> dict:
    from junior.computer.jobs import DEFAULT_SECONDS, MAX_RUNNING, MAX_SECONDS, list_jobs

    return {"jobs": [{**job, "output": ""} for job in list_jobs()],
            "limits": {"max_running": MAX_RUNNING, "default_seconds": DEFAULT_SECONDS,
                                            "max_seconds": MAX_SECONDS}}


@router.get("/api/computer/jobs/{job_id}")
def computer_job(job_id: str) -> dict:
    from junior.computer.jobs import get_job

    try:
        return get_job(job_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


@router.post("/api/computer/jobs/{job_id}/stop")
async def stop_computer_job(job_id: str, request: Request) -> dict:
    """The owner's direct Stop button is cancellation, allowed even while paused/off/in Plan mode."""
    from junior.computer.jobs import JobError

    try:
        row = await request.app.state.pc_jobs.stop(job_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except JobError as e:
        raise HTTPException(409, str(e)) from None
    audit("action", "computer.job.stop_requested", detail={"job_id": job_id, "source": "dashboard"})
    return row
