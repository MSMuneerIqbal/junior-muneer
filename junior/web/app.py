"""The dashboard: start posts, watch the agents work, then edit, approve and schedule."""

import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..agents import pipeline
from ..config import ProfileError, has_api_credentials, load_profile, settings
from ..platforms import PLATFORMS, enabled_platforms

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=HERE / "templates")


def _when(value: str | None) -> str:
    """'2026-10-14T18:30' -> '14 Oct, 18:30'"""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d %b, %H:%M")
    except ValueError:
        return value


templates.env.filters["when"] = _when

# --- login (only when DASHBOARD_PASSWORD is set, e.g. on a VPS) ---------------------------

_basic = HTTPBasic(auto_error=False)


def require_login(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    if not settings.password:
        return
    ok = (
        credentials is not None
        and secrets.compare_digest(credentials.username.encode(), settings.username.encode())
        and secrets.compare_digest(credentials.password.encode(), settings.password.encode())
    )
    if not ok:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Basic"})


# --- app ---------------------------------------------------------------------------------

def _scheduler(stop: threading.Event) -> None:
    while not stop.wait(30):
        try:
            db.promote_due_posts()
        except Exception:
            log.exception("Scheduler tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True, name="scheduler").start()
    yield
    stop.set()


app = FastAPI(title="Junior Muneer", lifespan=lifespan, dependencies=[Depends(require_login)])
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def page(request: Request, template: str, **context):
    try:
        profile, profile_error = load_profile(), ""
    except ProfileError as e:
        profile, profile_error = None, str(e)
    base = {
        "owner": profile.name if profile else "",
        "profile": profile,
        "profile_error": profile_error,
        "api_ok": has_api_credentials(),
        "msg": request.query_params.get("msg", ""),
        "platforms": PLATFORMS,
        "usage": db.usage_this_month(),
        "refresh": False,
    }
    return templates.TemplateResponse(request, template, base | context)


def go(url: str, msg: str = "") -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return RedirectResponse(url, status_code=303)


def _post_or_404(post_id: int) -> dict:
    post = db.get_post(post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    return post


def _clean(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


# --- dashboard ---------------------------------------------------------------------------

@app.get("/")
def dashboard(request: Request):
    db.promote_due_posts()
    groups = {s: db.list_posts(s) for s in ("ready", "review", "generating", "approved", "failed")}
    return page(
        request,
        "index.html",
        groups=groups,
        posted=db.list_posts("posted", limit=10),
        refresh=bool(groups["generating"]),
    )


# --- posts -------------------------------------------------------------------------------

@app.get("/new")
def new_post_form(request: Request):
    try:
        keys = [p.key for p in enabled_platforms(load_profile().platforms)]
    except ProfileError:
        keys = list(PLATFORMS)
    return page(request, "new.html", checked=keys)


@app.post("/new")
def create_posts(topic: str = Form(""), notes: str = Form(""), platforms: list[str] = Form([])):
    topic, notes = _clean(topic), _clean(notes)
    chosen = [key for key in platforms if key in PLATFORMS]
    if not topic:
        return go("/new", "Write a topic first.")
    if not chosen:
        return go("/new", "Pick at least one platform.")
    ids = []
    for key in chosen:
        post_id = db.create_post(key, topic, notes)
        pipeline.start(post_id)
        ids.append(post_id)
    if len(ids) == 1:
        return go(f"/posts/{ids[0]}")
    return go("/", f"The team is writing {len(ids)} posts. They'll show up under 'Needs your review'.")


@app.get("/posts/{post_id}")
def post_detail(request: Request, post_id: int):
    post = _post_or_404(post_id)
    return page(
        request,
        "post.html",
        post=post,
        platform=PLATFORMS[post["platform"]],
        refresh=post["status"] == "generating",
    )


@app.post("/posts/{post_id}/save")
def save_post(post_id: int, text: str = Form("")):
    _post_or_404(post_id)
    db.update_post(post_id, text=_clean(text))
    return go(f"/posts/{post_id}", "Saved.")


@app.post("/posts/{post_id}/approve")
def approve_post(post_id: int, text: str = Form(""), scheduled_at: str = Form("")):
    _post_or_404(post_id)
    text, when = _clean(text), scheduled_at.strip()[:16]
    if not text:
        return go(f"/posts/{post_id}", "The post is empty.")
    if when:
        try:
            datetime.strptime(when, "%Y-%m-%dT%H:%M")
        except ValueError:
            return go(f"/posts/{post_id}", "That date doesn't look right.")
    if when and when > db.now():
        db.update_post(post_id, text=text, status="approved", scheduled_at=when)
        return go("/", f"Scheduled for {_when(when)}. It moves to 'Ready to post' at that time.")
    db.update_post(post_id, text=text, status="ready", scheduled_at=None)
    return go(f"/posts/{post_id}", "Approved. Copy it and post it.")


@app.post("/posts/{post_id}/regenerate")
def regenerate_post(post_id: int, feedback: str = Form("")):
    post = _post_or_404(post_id)
    if post["status"] == "generating":
        return go(f"/posts/{post_id}", "The team is already working on this one.")
    feedback = _clean(feedback)
    db.update_post(
        post_id,
        status="generating",
        feedback=feedback,
        previous_text=post["text"] if feedback else "",
        trace=[],
        issues=[],
        score=None,
        error="",
    )
    pipeline.start(post_id)
    return go(f"/posts/{post_id}")


@app.post("/posts/{post_id}/unschedule")
def unschedule_post(post_id: int):
    _post_or_404(post_id)
    db.update_post(post_id, status="review", scheduled_at=None)
    return go(f"/posts/{post_id}", "Moved back to review.")


@app.post("/posts/{post_id}/posted")
def mark_posted(post_id: int):
    _post_or_404(post_id)
    db.update_post(post_id, status="posted", posted_at=db.now())
    return go("/", "Marked as posted. Nice work!")


@app.post("/posts/{post_id}/reject")
def reject_post(post_id: int):
    _post_or_404(post_id)
    db.update_post(post_id, status="rejected")
    return go("/", "Post thrown away.")


# --- ideas -------------------------------------------------------------------------------

@app.get("/ideas")
def ideas(request: Request):
    state = dict(pipeline.planner_state)
    return page(request, "ideas.html", ideas=db.list_ideas(), planner=state, refresh=state["running"])


@app.post("/ideas/suggest")
def suggest_ideas(count: int = Form(6), focus: str = Form("")):
    if not pipeline.start_planning(max(1, min(count, 10)), _clean(focus)):
        return go("/ideas", "The planner is already working.")
    return go("/ideas")


@app.post("/ideas/{idea_id}/write")
def write_from_idea(idea_id: int):
    idea = db.get_idea(idea_id)
    if idea is None or idea["platform"] not in PLATFORMS:
        raise HTTPException(404, "Idea not found")
    post_id = db.create_post(idea["platform"], idea["title"], idea["angle"])
    db.set_idea_status(idea_id, "used")
    pipeline.start(post_id)
    return go(f"/posts/{post_id}")


@app.post("/ideas/{idea_id}/dismiss")
def dismiss_idea(idea_id: int):
    db.set_idea_status(idea_id, "dismissed")
    return go("/ideas")
