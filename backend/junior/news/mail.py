"""The day's top 5 AI news, emailed to your own Gmail after the morning digest (through junior/mailer.py).

The text is the checked digest (fact guard: real links only), so it needs no approval; the
`gmail.news_to_self` rule is Auto, and Ask or Deny stops it. Pause stops it too.
"""

import html
import logging
from datetime import UTC, datetime, timedelta

from junior.audit import audit
from junior.mailer import MailError, configured, send_to_self
from junior.news.digest import latest_digest
from junior.permissions import decide
from junior.settings_store import all_settings, set_setting
from junior.timeutil import zone

log = logging.getLogger(__name__)

ACTION = "gmail.news_to_self"
RETRY_AFTER = timedelta(minutes=30)
_last_try: dict[str, datetime] = {}

NewsEmailError = MailError


class NoFreshNews(MailError):
    """Nothing new to deliver is a normal skip, not a failed SMTP attempt."""


def _day(iso: str, tz) -> str:
    return datetime.fromisoformat(iso).astimezone(tz).strftime("%d %b")


def news_email(digest: dict, timezone: str) -> tuple[str, str, str]:
    """Subject, plain text and HTML: the top 5 with a short summary, the section and the official sources (linked)."""
    tz = zone(timezone)
    built = datetime.fromisoformat(digest["built_at"]).astimezone(tz)
    top = digest.get("top") or []
    subject = f"Your top {len(top)} AI news · {built:%a %d %b}"
    text = [f"Your top {len(top)} AI news, {built:%A %d %B}. From your approved news sources.\n"]
    rows = []
    for n, item in enumerate(top, 1):
        sources = item["sources"]
        text.append(f"{n}. {item['headline']}\n   {item['summary']}")
        text += [f"   {s['name']} ({_day(s['date'], tz)}): {s['url']}" for s in sources]
        text.append("")
        links = " · ".join(
            f'<a href="{html.escape(s["url"])}" style="color:#c96442">{html.escape(s["name"])} · {_day(s["date"], tz)}</a>'
            for s in sources
        )
        rows.append(
            '<tr><td style="padding:14px 0;border-bottom:1px solid #eee">'
            f'<div style="font-size:12px;color:#888">{n} · {html.escape(item.get("section", ""))}</div>'
            f'<div style="font-size:16px;font-weight:600;margin:4px 0">{html.escape(item["headline"])}</div>'
            f'<div style="font-size:14px;line-height:1.5;color:#333">{html.escape(item["summary"])}</div>'
            f'<div style="font-size:12px;margin-top:6px">{links}</div></td></tr>'
        )
    text.append("More on the News page in Junior Muneer, or ask him for more.")
    body = (
        f'<h2 style="margin:0 0 4px">Your top {len(top)} AI news</h2>'
        f'<p style="margin:0 0 8px;color:#888;font-size:13px">{built:%A %d %B} · from your approved news sources</p>'
        f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        '<p style="color:#888;font-size:12px;margin-top:16px">More on the News page, or ask Junior Muneer for more. '
        "Turn this email off in Settings → News.</p>"
    )
    return subject, "\n".join(text), body


async def send_news_email(digest: dict | None = None, *, by_you: bool = False) -> str:
    """Send the top 5 now. `by_you`: you clicked "Send it now" (that click is your OK, even with the rule on Ask).
    Raises MailError with the reason when it can't."""
    if not configured():
        raise MailError("Gmail isn't set up: add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to backend/.env, then restart.")
    decision = decide(ACTION, from_outside=False)
    if decision.rule == "deny":
        raise MailError(f"Not sent: {decision.reason}")
    if decision.rule == "ask" and not by_you:
        raise MailError(f"Not sent by itself: {decision.reason}")
    if decision.held and not by_you:
        raise MailError("Not sent: Junior Muneer is paused.")
    digest = digest or latest_digest("ai")
    if not digest or not digest.get("top"):
        raise NoFreshNews("No verified AI news from the last three days. Refresh News; older stories will not be emailed.")
    settings = all_settings()
    from junior.news.freshness import recent_sections
    from junior.news.delivery import claim, finish
    digest = {**digest, "sections": recent_sections(digest.get("sections", []), datetime.now(UTC))}
    batch, selected = claim(digest)
    if not selected:
        raise NoFreshNews("No new, undelivered AI stories from the last three days. Nothing was emailed again.")
    digest["top"] = selected
    subject, text, body = news_email(digest, settings["timezone"])
    try:
        address = await send_to_self(subject, text, body)
    except BaseException:
        finish(batch, "unclear")
        raise
    finish(batch, "sent")
    today = datetime.now(UTC).astimezone(zone(settings["timezone"])).date().isoformat()
    set_setting("news_emailed_on", today)
    audit("action", "news_email", detail={"items": len(digest["top"]), "digest": digest.get("id"), "by_you": by_you})
    return f"Sent the top {len(digest['top'])} AI news to {address}."


async def daily_news_email(now: datetime | None = None) -> bool:
    """Scheduler job: once a day, after today's AI digest is built, email its top 5."""
    settings = all_settings()
    if not settings["news_email_enabled"] or settings["paused"] or not configured():
        return False
    if decide(ACTION, from_outside=False).rule != "auto":
        return False  # your rule says Ask or Deny: no email by itself
    now = now or datetime.now(UTC)
    tz = zone(settings["timezone"])
    today = now.astimezone(tz).date()
    if settings["news_emailed_on"] == today.isoformat():
        return False
    digest = latest_digest("ai")
    if not digest or datetime.fromisoformat(digest["built_at"]).astimezone(tz).date() != today:
        return False  # waits for the morning digest
    if "ai" in _last_try and now - _last_try["ai"] < RETRY_AFTER:
        return False
    _last_try["ai"] = now
    try:
        await send_news_email(digest)
    except NoFreshNews:
        audit("action", "news_email_skipped", detail={"reason": "No new verified stories within three days."})
        return False
    except MailError as e:
        log.warning("Daily news email: %s", e)
        audit("action", "news_email", result="error", detail={"error": str(e)})
        return False
    return True
