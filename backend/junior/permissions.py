"""Permission rules: Ask / Auto / Deny for every outgoing action (PLAN.md section 8).

Every action has a type such as `linkedin.post` or `gmail.send`, and each type has a rule:

    ask    it goes into your approval queue; nothing happens until you click
    auto   it runs by itself (still logged, checked and limited per day)
    deny   it never runs

On top of the rules:
    - Locked types keep their default; you can't change them (merges, deletes, terminal...).
    - Anything caused by outside content (emails, comments, pastes, web pages) is at
      least Ask, and "Always allow" is never offered for it.
    - The global mode: "Ask everything" turns every Auto into Ask; "Pause everything"
      (the pause switch) holds everything for you.
    - Deny always wins.
    - "Run at most once": an action is claimed by a unique key before it runs, so a
      retry or a double click can never send it twice.

    GET /api/permissions                   mode and every action type with its rule
    PUT /api/permissions/mode   {"mode"}   rules (Auto) · ask_all (Manual) · plan
    PUT /api/permissions/rules/{type}  {"rule"}   change one rule (refused when locked)
"""

import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from junior.audit import audit
from junior.db import ActionRun, session_scope
from junior.db.models import utcnow
from junior.pause import is_paused
from junior.settings_store import get_setting, set_setting

router = APIRouter()

Rule = Literal["ask", "auto", "deny"]
# rules = "Auto" (your rules decide) · ask_all = "Manual" (everything asks)
# plan = "Plan" (he shows a plan first; nothing is drafted or queued until you switch mode)
Mode = Literal["rules", "ask_all", "plan"]
RULES: tuple[Rule, ...] = ("ask", "auto", "deny")
MODES: tuple[Mode, ...] = ("rules", "ask_all", "plan")

_ACTION_TYPE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


@dataclass(frozen=True)
class ActionType:
    key: str
    label: str
    group: str
    default: Rule
    locked: bool = False
    note: str = ""


def _t(key, label, group, default, locked=False, note=""):
    return ActionType(key, label, group, default, locked, note)


# Reading, drafting, chat and search are not outgoing actions: they need no rule.
# Copy-and-paste items (Upwork, Fiverr, LinkedIn comments, X...) are sent by you, never by the system.
CATALOG: dict[str, ActionType] = {
    t.key: t
    for t in (
        _t("linkedin.post", "Post on LinkedIn", "Social", "ask"),
        _t("facebook.page.post", "Post on your Facebook Page", "Social", "ask"),
        _t("instagram.post", "Post on Instagram", "Social", "ask"),
        _t("facebook.comment.reply", "Reply to a Facebook comment", "Social", "ask", True,
           "Replies answer outside content, so they always wait for you."),
        _t("instagram.comment.reply", "Reply to an Instagram comment", "Social", "ask", True,
           "Replies answer outside content, so they always wait for you."),
        _t("gmail.draft", "Make a Gmail draft (it waits for your OK to send)", "Email", "auto",
           note="Only a draft in your Gmail Drafts; sending is the next rule."),
        _t("gmail.send", "Send a new email", "Email", "ask",
           note="Auto: he sends it as soon as you ask, no card to approve. Ask: a draft waits for your Approve."),
        _t("gmail.reply", "Reply to an email", "Email", "ask", True,
           "Replies answer outside content, so they always wait for you."),
        _t("gmail.to_self", "Email yourself what you ask for (news, drafts, notes)", "Email", "auto",
           note="Only ever to your own Gmail address, and only when you ask. Ask or Deny stops it."),
        _t("whatsapp.to_self", "WhatsApp yourself what you ask for (text, documents)", "WhatsApp", "auto",
           note="Only ever to your own WhatsApp number, and only when you ask."),
        _t("gmail.news_to_self", "Email yourself the daily top 5 AI news", "Email", "auto",
           note="Only ever to your own Gmail address. Ask or Deny stops the email."),
        _t("google.docs.create", "Create a Google Doc in your Drive", "Google", "auto",
           note="A new doc only; your existing docs are only read."),
        _t("google.sheets.create", "Create a Google Sheet in your Drive", "Google", "auto",
           note="A new sheet only; your existing sheets are only read."),
        _t("google.slides.create", "Create Google Slides in your Drive", "Google", "ask",
           note="A new presentation only; researched content always waits for approval."),
        _t("google.drive.save", "Save a file you sent to your Google Drive", "Google", "auto",
           note="Only adds new files; never changes or deletes yours."),
        _t("google.drive.share", "Share a Drive file with anyone who has its link", "Google", "ask",
           note="The card specifies public viewing or public editing. Anyone with an edit link can change the file."),
        _t("google.calendar.create", "Add an event to your Google Calendar", "Google", "auto",
           note="Only when you ask, on your own calendar; nobody is invited."),
        _t("maintenance.update", "Install a reviewed Junior update and restart", "Maintenance", "ask", True,
           "Exact revision, clean source, isolated checks, database backup and rollback. Calls/jobs are interrupted."),
        _t("maintenance.code.test", "Run tests on reviewed generated source", "Maintenance", "ask", True,
           "Native tests can do anything your account can. Review the full diff; clean environment and separate source are not a sandbox."),
        _t("maintenance.code.apply", "Apply a tested local source proposal", "Maintenance", "ask", True,
           "Only exact unchanged targets after passed checks. No commit, push or automatic restart."),
        _t("maintenance.code.rollback", "Restore a proposal's saved original source", "Maintenance", "ask", True,
           "Refuses if an applied file has changed since. No automatic rollback of your later work."),
        _t("skills.learn", "Save a learned workflow as a reusable skill", "Skills", "ask", True,
           "Review its steps before saving. Skills never grant tool permissions or run scripts by themselves."),
        _t("github.issue.create", "Create a GitHub issue", "GitHub", "ask"),
        _t("github.comment", "Comment on GitHub", "GitHub", "ask"),
        _t("github.pr.open", "Open a pull request", "GitHub", "ask"),
        _t("github.push.branch", "Push to a branch", "GitHub", "ask"),
        _t("github.merge", "Merge a pull request", "GitHub", "ask", True),
        _t("github.push.main", "Push to main", "GitHub", "ask", True),
        _t("github.release", "Create a release", "GitHub", "ask", True),
        _t("github.repo.delete", "Delete a repository", "GitHub", "deny", True),
        _t("github.branch.delete", "Delete a branch", "GitHub", "deny", True),
        _t("github.force_push", "Force-push", "GitHub", "deny", True),
        _t("github.settings", "Change repo visibility or settings", "GitHub", "deny", True),
        _t("computer.read", "Look in your allowed folders and read files", "Your computer", "auto",
           note="Only in the folders you allow (Settings → Computer) or a path you type yourself; never keys or passwords. Deny turns it off."),
        _t("computer.write", "Create or change a file, make a folder", "Your computer", "ask",
           note="The card shows the new text; you can edit it before you approve."),
        _t("computer.move", "Move or rename a file or folder", "Your computer", "ask"),
        _t("computer.delete", "Delete a file or folder (to the Recycle Bin)", "Your computer", "ask",
           note="Always to the Recycle Bin, so you can restore it. Deleting for good is never allowed."),
        _t("computer.run", "Run a terminal command on your PC", "Your computer", "ask", True,
           "A command can do anything your account can, so you check every one. Dangerous ones are refused anyway."),
        _t("computer.job.stop", "Stop a PC command job", "Your computer", "ask", True,
           "Chat requests wait for your OK. You can also press Stop beside an owned job in Settings → Computer."),
        _t("computer.desktop.observe", "Observe allowed app windows and screenshots", "Your computer", "auto",
           note="Only after desktop opt-in and app selection in Settings → Computer; at most four captures per message."),
        _t("computer.desktop.input", "Focus, click or type in an observed app window", "Your computer", "ask", True,
           "One reviewed action per fresh snapshot; foreground and control identity are checked again. No terminal/browser/security UI."),
        _t("computer.browser.observe", "Read the isolated browser page", "Your computer", "auto",
           note="Only after browser opt-in and exact website scope; page data is untrusted."),
        _t("computer.browser.input", "Navigate, click, fill or download in the browser", "Your computer", "auto",
           note="Auto runs user-directed actions; Manual asks. Website text is untrusted; protected actions remain blocked."),
        _t("files.archive_whatsapp", "Upload a prepared ZIP privately to Drive and send its link to your WhatsApp", "Files", "ask",
           note="Shows the folder, archive size and destination. Drive-save and WhatsApp-to-self rules also apply."),
        _t("system.delete", "Delete anything", "Never", "deny", True),
        _t("system.payment", "Make a payment", "Never", "deny", True),
        _t("system.account_settings", "Change account settings", "Never", "deny", True),
        _t("system.password", "Type a password", "Never", "deny", True),
    )
}


class RuleChangeError(Exception):
    """A rule change that isn't allowed. The message says why."""


def _check_type(action_type: str) -> None:
    if not _ACTION_TYPE.match(action_type):
        raise RuleChangeError(f"{action_type!r} isn't an action type; use dotted names like gmail.send.")


ACTION_CHANNEL = ContextVar("junior_action_channel", default="dashboard")


def get_mode(channel: str | None = None) -> Mode:
    if (channel or ACTION_CHANNEL.get()) == "whatsapp":
        mode = get_setting("whatsapp_action_mode")
        return mode if mode in ("rules", "ask_all") else "ask_all"
    mode = get_setting("permission_mode")
    return mode if mode in MODES else "rules"


def set_mode(mode: str) -> None:
    if mode not in MODES:
        raise RuleChangeError(f"Mode must be one of {list(MODES)}.")
    if mode != get_mode():
        set_setting("permission_mode", mode)
        audit("setting", "permission_mode", detail={"mode": mode})


def _saved_rules() -> dict[str, str]:
    rules = get_setting("permission_rules")
    return rules if isinstance(rules, dict) else {}


def rule_for(action_type: str) -> Rule:
    """Your rule for a type (before the mode and outside-content checks)."""
    _check_type(action_type)
    known = CATALOG.get(action_type)
    if known and known.locked:
        return known.default
    saved = _saved_rules().get(action_type)
    if saved in RULES:
        return saved  # type: ignore[return-value]
    return known.default if known else "ask"  # anything not listed: Ask


def set_rule(action_type: str, rule: str) -> None:
    _check_type(action_type)
    if rule not in RULES:
        raise RuleChangeError(f"Rule must be one of {list(RULES)}.")
    known = CATALOG.get(action_type)
    if known and known.locked:
        raise RuleChangeError(f"{known.label} is locked to {known.default.capitalize()}; it can't be changed.")
    before = rule_for(action_type)
    rules = _saved_rules()
    rules[action_type] = rule
    set_setting("permission_rules", rules)
    if before != rule:
        audit("setting", "permission_rule", detail={"type": action_type, "from": before, "to": rule})


@dataclass(frozen=True)
class Decision:
    rule: Rule
    reason: str
    # Show "Approve + always allow this kind"?
    can_always_allow: bool = False
    # Paused: allowed in principle, but nothing runs until you resume.
    held: bool = False


def decide(action_type: str, *, from_outside: bool, channel: str | None = None, browser_directed: bool = False) -> Decision:
    """What happens to one action. Deny wins; outside content and "Ask everything" turn Auto into Ask."""
    rule = rule_for(action_type)
    known = CATALOG.get(action_type)
    locked = bool(known and known.locked)
    held = is_paused()

    if rule == "deny":
        why = "it's locked to Deny" if locked else "your rule is Deny"
        return Decision("deny", f"Never runs: {why}.")
    if action_type == "computer.browser.input" and not browser_directed:
        return Decision("ask", "This browser action needs your review because its target or content was not established by your request.", False, held)
    can_always_allow = not locked and not from_outside
    if from_outside and not (action_type == "computer.browser.input" and browser_directed):
        return Decision("ask", "It comes from outside content, so it always waits for you.", False, held)
    if rule == "auto" and get_mode(channel) in ("ask_all", "plan"):
        return Decision("ask", "Manual mode: everything waits for you.", can_always_allow, held)
    if rule == "auto":
        return Decision("auto", "Your rule is Auto.", False, held)
    why = "it's locked to Ask" if locked else "your rule is Ask"
    return Decision("ask", f"Waits for you: {why}.", can_always_allow, held)


def plan_mode_refusal() -> str | None:
    """In Plan mode nothing is drafted or queued: he shows the plan and waits."""
    if get_mode() == "plan":
        return (
            "NOT done: Plan mode is on. Show your plan in a few short steps instead, and tell "
            "them to switch the mode (under the message box) to Auto or Manual to go ahead."
        )
    return None


# --- Run at most once -------------------------------------------------------


class AlreadyRun(Exception):
    """This action was already claimed; running it again could send it twice."""


def claim_run(key: str, action_type: str) -> int:
    """Claim the right to run an action once. A second claim with the same key raises AlreadyRun."""
    _check_type(action_type)
    try:
        with session_scope() as s:
            run = ActionRun(key=key, action_type=action_type, status="running")
            s.add(run)
            s.flush()
            return run.id
    except IntegrityError:
        raise AlreadyRun(f"{action_type} {key!r} already ran (or is running); not running it again.") from None


def finish_run(run_id: int, status: Literal["done", "failed", "check_manually"], detail: dict | None = None) -> None:
    """Record how a claimed run ended. A failed run stays claimed: you retry it on purpose, by hand."""
    with session_scope() as s:
        run = s.get(ActionRun, run_id)
        run.status = status
        run.detail = detail or {}
        run.finished_at = utcnow()


# --- API ---------------------------------------------------------------------


class ModeBody(BaseModel):
    mode: Mode


class RuleBody(BaseModel):
    rule: Rule


@router.get("/api/permissions")
def get_permissions() -> dict:
    custom = [k for k in _saved_rules() if k not in CATALOG]
    types = [
        {
            "type": t.key,
            "label": t.label,
            "group": t.group,
            "rule": rule_for(t.key),
            "default": t.default,
            "locked": t.locked,
            "note": t.note,
        }
        for t in CATALOG.values()
    ] + [
        {"type": k, "label": k, "group": "Other", "rule": rule_for(k), "default": "ask", "locked": False, "note": ""}
        for k in sorted(custom)
    ]
    return {"mode": get_mode(), "paused": is_paused(), "types": types}


@router.put("/api/permissions/mode")
def put_mode(body: ModeBody) -> dict:
    set_mode(body.mode)
    return get_permissions()


@router.put("/api/permissions/rules/{action_type}")
def put_rule(action_type: str, body: RuleBody) -> dict:
    try:
        set_rule(action_type, body.rule)
    except RuleChangeError as e:
        raise HTTPException(400, str(e)) from None
    return get_permissions()
