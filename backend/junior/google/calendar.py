"""Google Calendar: add an event to your own calendar, and see what's coming.

Events go on your primary calendar only, with nobody invited: there is no attendees field at all.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta

from junior.google.auth import GoogleError, call, has_scope, is_connected
from junior.timeutil import zone

log = logging.getLogger(__name__)

EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MAX_DAYS = 60


def _parse_local(text: str, tz_name: str) -> datetime:
    """'2026-11-05 10:00' or '2026-11-05T10:00' in your time zone."""
    text = text.strip().replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise GoogleError(f"I couldn't read the time {text!r}; use YYYY-MM-DD HH:MM.") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=zone(tz_name))


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        raise GoogleError(f"I couldn't read the date {text!r}; use YYYY-MM-DD.") from None


async def add_event(
    title: str,
    start: str,
    end: str,
    all_day: bool,
    location: str,
    notes: str,
    reminder_minutes: int | None,
    tz_name: str,
) -> dict:
    """Put an event on your calendar. Returns Google's event (with its htmlLink)."""
    body: dict = {"summary": " ".join(title.split())[:300] or "Event"}
    if all_day:
        first = _parse_day(start)
        last = _parse_day(end) if end.strip() else first
        if last < first:
            raise GoogleError("The event ends before it starts.")
        body["start"] = {"date": first.isoformat()}
        body["end"] = {"date": (last + timedelta(days=1)).isoformat()}  # Google's end date is exclusive
    else:
        begins = _parse_local(start, tz_name)
        ends = _parse_local(end, tz_name) if end.strip() else begins + timedelta(hours=1)
        if ends <= begins:
            raise GoogleError("The event ends before it starts.")
        body["start"] = {"dateTime": begins.isoformat(), "timeZone": tz_name}
        body["end"] = {"dateTime": ends.isoformat(), "timeZone": tz_name}
    if location.strip():
        body["location"] = location.strip()[:500]
    if notes.strip():
        body["description"] = notes.strip()[:4000]
    if reminder_minutes is not None:
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": max(0, min(reminder_minutes, 40320))}]}
    return await call("POST", EVENTS, json=body)


async def upcoming(days: int, tz_name: str, now: datetime | None = None, query: str = "") -> list[dict]:
    """Your events from now for this many days, soonest first."""
    now = now or datetime.now(UTC)
    days = max(1, min(days, MAX_DAYS))
    params = {
        "timeMin": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "timeMax": (now + timedelta(days=days)).astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
        "timeZone": tz_name,
    }
    if query.strip():
        params["q"] = query.strip()[:100]
    return (await call("GET", EVENTS, params=params)).get("items", [])


def describe(event: dict, tz_name: str) -> str:
    """One line: when, what, where."""
    tz = zone(tz_name)
    start, end = event.get("start", {}), event.get("end", {})
    if "date" in start:
        first = date.fromisoformat(start["date"])
        last = date.fromisoformat(end.get("date", start["date"])) - timedelta(days=1)
        when = first.strftime("%a %d %b") + (f" to {last.strftime('%a %d %b')}" if last > first else "") + ", all day"
    else:
        begins = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone(tz)
        when = begins.strftime("%a %d %b, %H:%M")
        if "dateTime" in end:
            when += "-" + datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00")).astimezone(tz).strftime("%H:%M")
    line = f"{when}: {event.get('summary', '(no title)')}"
    if event.get("location"):
        line += f" (at {event['location']})"
    return re.sub(r"\s+", " ", line)


async def today_for_briefing(tz_name: str, now: datetime | None = None) -> str:
    """Today's events for the morning briefing, or '' (not connected, or Google didn't answer: the briefing goes on)."""
    if not (is_connected() and has_scope("calendar.events")):
        return ""
    now = now or datetime.now(UTC)
    local = now.astimezone(zone(tz_name))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        events = await upcoming(1, tz_name, now=midnight)
    except GoogleError as e:
        log.warning("Briefing: couldn't read the calendar: %s", e)
        return ""
    return "\n".join(f"- {describe(e, tz_name)}" for e in events)
