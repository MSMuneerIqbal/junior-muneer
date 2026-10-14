"""The global "Pause everything" switch. Stored in settings, so it survives a restart.

While paused: no background work (summaries, schedules) and no actions. Chat still works.

    GET  /api/pause                    {"paused": bool}
    POST /api/pause  {"paused": bool}  switch it
"""

from fastapi import APIRouter
from pydantic import BaseModel

from junior.audit import audit
from junior.settings_store import get_setting, set_setting

router = APIRouter()


class PausedError(Exception):
    """Raised by anything that must not run while paused (background work, actions)."""


def is_paused() -> bool:
    return bool(get_setting("paused"))


def set_paused(paused: bool) -> None:
    if paused != is_paused():
        set_setting("paused", paused)
        audit("setting", "paused" if paused else "resumed")


def ensure_not_paused(what: str) -> None:
    if is_paused():
        raise PausedError(f"{what} skipped: everything is paused.")


class PauseState(BaseModel):
    paused: bool


@router.get("/api/pause", response_model=PauseState)
def get_pause() -> PauseState:
    return PauseState(paused=is_paused())


@router.post("/api/pause", response_model=PauseState)
def post_pause(body: PauseState) -> PauseState:
    set_paused(body.paused)
    return PauseState(paused=is_paused())
