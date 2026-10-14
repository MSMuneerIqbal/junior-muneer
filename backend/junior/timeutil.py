"""Time helpers. Everything is stored in UTC and shown in your time zone."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def start_of_today_utc(tz_name: str, now: datetime | None = None) -> datetime:
    """Midnight today in your time zone, as a UTC time."""
    tz = zone(tz_name)
    local_now = (now or datetime.now(UTC)).astimezone(tz)
    midnight = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    return midnight.astimezone(UTC)


def start_of_day_utc(tz_name: str, days_ago: int, now: datetime | None = None) -> datetime:
    return start_of_today_utc(tz_name, now) - timedelta(days=days_ago)


def local_now_text(tz_name: str) -> str:
    return datetime.now(UTC).astimezone(zone(tz_name)).strftime("%A %d %B %Y, %H:%M")
