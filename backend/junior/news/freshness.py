"""Freshness is checked again at display/delivery time, including pre-upgrade digests."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import re

from junior.news.reader import WINDOW_DAYS, normalize_url

POLICY_VERSION = 2


def recent_sections(sections, now):
    oldest = now - timedelta(days=WINDOW_DAYS)
    result = []
    for section in deepcopy(sections):
        items = []
        for item in section.get("items", []):
            sources = item.get("sources") or []
            try:
                dates = [datetime.fromisoformat(s["date"].replace("Z", "+00:00")) for s in sources]
                valid = sources and all(d.tzinfo is not None and oldest <= d <= now for d in dates)
            except (KeyError, ValueError, TypeError, AttributeError):
                valid = False
            if valid:
                item["date"] = max(dates).isoformat()
                items.append(item)
        section["items"] = sorted(items, key=lambda i: i["date"], reverse=True)
        result.append(section)
    return result


def story_keys(item):
    """Track original URLs/titles, so a newly worded AI headline cannot repeat yesterday's story."""
    values = []
    for source in item.get("sources", []):
        if source.get("url"):
            values.append("url:" + normalize_url(source["url"]))
        title = re.sub(r"\W+", " ", source.get("title", "").casefold()).strip()
        if title:
            values.append("title:" + title)
    return {hashlib.sha256(value.encode()).hexdigest() for value in values}
