"""The Safety Guard (P3-01): a rule check in code, not AI, before every action.

It blocks a send when anything is off:
    - it isn't an approved API item, or the action type's rule is now Deny;
    - the rule now needs your OK (Ask, Manual or Plan mode, outside content) but you didn't approve it yourself;
    - everything is paused;
    - the text isn't exactly the text that was approved;
    - it breaks a hard limit (too long, a needed image is missing, empty);
    - it contains something that must never go out (keys, tokens, passwords, unfinished placeholders);
    - today's limit of posts on that platform is reached.
"""

import re

from sqlalchemy import func, select

from junior.approvals import PLATFORM_LABELS, _needs_image
from junior.db import ApprovalItem, session_scope
from junior.permissions import decide
from junior.settings_store import get_setting
from junior.timeutil import start_of_today_utc

# Things that must never be posted, whatever the text says.
NEVER_SEND = [
    (re.compile(r"\bsk-(proj-)?[A-Za-z0-9_-]{20,}"), "an API key"),
    (re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"), "a GitHub token"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS key"),
    (re.compile(r"\bEAA[A-Za-z0-9]{30,}"), "a Meta access token"),
    (re.compile(r"\b(password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE), "a password"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
]
PLACEHOLDERS = re.compile(r"\[(link|url|name|insert[^\]]*|your [^\]]*)\]|\{\{[^}]*\}\}|\bTODO\b|lorem ipsum", re.IGNORECASE)


def posted_today(platform: str) -> int:
    """API posts sent on this platform today (your local day)."""
    since = start_of_today_utc(get_setting("timezone"))
    with session_scope() as s:
        return s.scalar(
            select(func.count())
            .select_from(ApprovalItem)
            .where(
                ApprovalItem.kind == "api",
                ApprovalItem.platform == platform,
                ApprovalItem.status == "posted",
                ApprovalItem.posted_at >= since,
            )
        ) or 0


def check(item: ApprovalItem, text: str) -> list[str]:
    """Problems that block sending, in plain words. Empty means it may go."""
    problems: list[str] = []
    label = PLATFORM_LABELS.get(item.platform, item.platform)
    if item.kind != "api" or not item.action_type:
        return ["This is a copy-and-paste item: you send it yourself."]
    if item.status != "approved":
        return [f"It isn't approved (it's {item.status.replace('_', ' ')})."]

    decision = decide(item.action_type, from_outside=item.from_outside)
    if decision.rule == "deny":
        problems.append(decision.reason)
    elif decision.held:
        problems.append("Everything is paused. It goes out after you resume.")
    elif decision.rule == "ask" and item.meta.get("approved_by") != "you":
        problems.append(f"It needs your OK first ({decision.reason.rstrip('.')}).")
    for key in item.meta.get("required_actions", []):
        required = decide(key, from_outside=item.from_outside)
        if required.rule == "deny" or required.held:
            problems.append(required.reason)
        elif required.rule == "ask" and item.meta.get("approved_by") != "you":
            problems.append(f"It also needs your OK for {key}.")

    approved = item.meta.get("approved_text")
    if approved is None or text != approved or item.text != approved:
        problems.append("The text isn't exactly the text that was approved.")
    if not text.strip():
        problems.append("The text is empty.")

    from junior.playbooks import load_playbooks

    book = load_playbooks().get(item.platform)
    if book and len(text) > book.max_chars:
        problems.append(f"Too long for {label}: {len(text)} characters, the limit is {book.max_chars}.")
    if _needs_image(item.platform, item.item_type):
        from junior.images import images_for

        if not images_for([item.id]).get(item.id):
            problems.append(f"{label} posts need an image.")

    computer = item.platform == "computer"  # a file or a command on your PC: TODOs and "pwd = ..." are normal there
    for pattern, what in NEVER_SEND:
        if computer and what == "a password":
            continue
        if pattern.search(text):
            problems.append(f"It contains {what}. " + ("Junior never writes or runs that." if computer else "That must never be posted."))
    if computer or item.platform in {"skills", "maintenance"}:
        return problems
    if PLACEHOLDERS.search(text):
        problems.append("It still has a placeholder (like [link] or TODO) to fill in.")

    limit = get_setting("api_posts_per_day")
    if limit is not None and posted_today(item.platform) >= limit:
        problems.append(f"Today's limit is reached: {limit} posts on {label}. Raise it in Settings → Permissions.")
    return problems

