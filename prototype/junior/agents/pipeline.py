"""How the team works together, in background threads so the dashboard stays responsive.

Post:  Writer -> Checker (sends back up to 2 times) -> Humanizer -> final Checker -> owner's review
Ideas: Social Media Manager -> idea list on the dashboard
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from .. import db
from ..config import ProfileError, load_profile
from ..llm import LLMError
from ..platforms import PLATFORMS, enabled_platforms
from . import checker, humanizer, planner, writer
from .common import Brief

log = logging.getLogger(__name__)

MAX_REVISIONS = 2

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="junior")


# --- posts -------------------------------------------------------------------------------

def start(post_id: int) -> None:
    _executor.submit(_write_safely, post_id)


def _write_safely(post_id: int) -> None:
    try:
        write_post(post_id)
    except (LLMError, ProfileError) as e:
        db.update_post(post_id, status="failed", error=str(e))
    except Exception as e:
        log.exception("Post %s failed", post_id)
        db.update_post(post_id, status="failed", error=f"Unexpected error: {e}")


def write_post(post_id: int) -> None:
    post = db.get_post(post_id)
    brief = Brief(
        profile=load_profile(),
        platform=PLATFORMS[post["platform"]],
        topic=post["topic"],
        notes=post["notes"],
        feedback=post["feedback"],
        previous_text=post["previous_text"],
        examples=db.approved_examples(post["platform"], post_id),
    )
    trace: list[dict] = []

    def step(agent: str, summary: str, text: str = "", notes: list[str] | None = None) -> None:
        # Saved after every step so the dashboard can show progress live.
        trace.append({"agent": agent, "summary": summary, "text": text, "notes": notes or []})
        db.update_post(post_id, trace=trace)

    draft = writer.write(brief)
    text, visual = draft.text, draft.visual_idea
    step("Writer", "First draft", text, [f"Visual idea: {visual}"])

    for round_no in range(1, MAX_REVISIONS + 1):
        check = checker.review(brief, text)
        step("Checker", f"Score {check.score}/10, {'passed' if check.passes else 'sent back'}", notes=check.issues)
        if check.passes:
            break
        draft = writer.revise(brief, text, check.issues)
        text, visual = draft.text, draft.visual_idea or visual
        step("Writer", f"Revision {round_no}", text)

    human = humanizer.humanize(brief, text)
    text = human.text
    step("Humanizer", "Made it sound like you", text, human.changes)

    final = checker.review(brief, text)
    step("Checker", f"Final check: {final.score}/10", notes=final.issues)
    if not final.passes:
        human = humanizer.humanize(brief, text, final.issues)
        text = human.text
        step("Humanizer", "Fixed what the final check found", text, human.changes)
        final = checker.review(brief, text)
        step("Checker", f"Final check: {final.score}/10", notes=final.issues)

    db.update_post(
        post_id, status="review", text=text, visual_idea=visual, score=final.score, issues=final.issues, error=""
    )


# --- ideas -------------------------------------------------------------------------------

planner_state = {"running": False, "error": "", "added": 0}
_planner_lock = threading.Lock()


def start_planning(count: int, focus: str) -> bool:
    """Returns False if the planner is already busy."""
    with _planner_lock:
        if planner_state["running"]:
            return False
        planner_state.update(running=True, error="", added=0)
    _executor.submit(_plan, count, focus)
    return True


def _plan(count: int, focus: str) -> None:
    try:
        profile = load_profile()
        platforms = enabled_platforms(profile.platforms)
        ideas = planner.suggest(profile, platforms, count, focus, db.recent_topics())
        db.add_ideas([idea.model_dump() for idea in ideas])
        planner_state["added"] = len(ideas)
    except (LLMError, ProfileError) as e:
        planner_state["error"] = str(e)
    except Exception as e:
        log.exception("Planner failed")
        planner_state["error"] = f"Unexpected error: {e}"
    finally:
        planner_state["running"] = False
