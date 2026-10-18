"""The fact guard (P2b-01b): code, not AI, decides what reaches you.

The news agent may only point to articles by their number in the list of articles that were
really read today. Links and dates are attached here, from those articles, so the AI can't
invent a link or change one. An item is removed when:
    - it points to no article that was read (an invented item),
    - one of its articles is older than 15 days (or dated in the future),
    - it contains a number that none of its articles contains (an invented figure),
    - its section isn't one of the digest's sections.
Any link the AI writes into the text is removed. Answers to questions keep only links to
official sites.
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from junior.news.reader import WINDOW_DAYS, Article
from junior.news.sources import site_of

MAX_ITEMS_PER_SECTION = 8

SECTIONS = {
    "ai": {
        "models": "New models and releases",
        "benchmarks": "Benchmarks and who's on top",
        "agents": "Agents and tools",
        "business": "Business moves",
    },
    "pakistan": {
        "top": "Top stories",
        "trending": "Trending online",
        "tech": "Tech, internet and freelancing",
        "economy": "Economy that affects you",
    },
}


# ---- what the news agent returns ---------------------------------------------------


class DigestItemIn(BaseModel):
    article_ids: list[int] = Field(description="The numbers of the articles this item is based on.")
    headline: str = Field(description="A short, plain headline.")
    summary: str = Field(description="One or two sentences: only what the articles say.")
    importance: int | None = Field(
        default=None, description="How much this matters to the reader, 1 (minor) to 10 (the biggest news of the period)."
    )


class DigestSectionIn(BaseModel):
    key: str = Field(description="The section's key from the list you were given.")
    items: list[DigestItemIn]


class DigestIn(BaseModel):
    sections: list[DigestSectionIn]


# ---- checks ------------------------------------------------------------------------

# A bare link; it ends before brackets, quotes and the punctuation after it.
_URL = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]\"']*[^\s<>()\[\]\"'.,;:!?]", re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Numbers in a text, written the same way ("1,200" and "1200" match; "91.2" stays "91.2")."""
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def strip_links(text: str) -> tuple[str, int]:
    """Remove links the AI wrote into a headline or summary (links only ever come from articles)."""
    text, n1 = _MD_LINK.subn(r"\1", text)
    text, n2 = _URL.subn("", text)
    if not n1 + n2:
        return text, 0
    text = re.sub(r"\(\s*\)", "", text)  # "()" left where a link was
    return re.sub(r"\s{2,}", " ", text).strip().rstrip(":–-").strip(), n1 + n2


def _allowed_numbers(articles: list[Article]) -> set[str]:
    allowed: set[str] = set()
    for a in articles:
        allowed |= _numbers(f"{a.source} {a.title} {a.summary}")
        d = a.published
        allowed |= {str(d.year), str(d.day), f"{d.day:02d}", str(d.month)}
    return allowed


def guard_digest(raw: DigestIn, articles: dict[int, Article], topic: str, now: datetime) -> dict:
    """The checked digest: sections of items with real links and dates, plus what was removed."""
    oldest, newest = now - timedelta(days=WINDOW_DAYS), now + timedelta(days=1)
    names = SECTIONS[topic]
    sections: dict[str, list[dict]] = {key: [] for key in names}
    removed: list[dict] = []

    def remove(item: DigestItemIn, why: str) -> None:
        removed.append({"headline": item.headline[:200], "reason": why})

    for section in raw.sections:
        for item in section.items:
            if section.key not in names:
                remove(item, f"unknown section {section.key!r}")
                continue
            used = [articles[i] for i in dict.fromkeys(item.article_ids) if i in articles]
            if not used:
                remove(item, "not based on an article that was read")
                continue
            if any(not oldest <= a.published <= newest for a in used):
                remove(item, "uses a story older than 15 days")
                continue
            headline, n1 = strip_links(item.headline)
            summary, n2 = strip_links(item.summary)
            if not headline:
                remove(item, "no headline")
                continue
            invented = _numbers(f"{headline} {summary}") - _allowed_numbers(used)
            if invented:
                remove(item, f"has a number its sources don't have ({', '.join(sorted(invented))})")
                continue
            sources = sorted(
                (
                    {"name": a.source, "title": a.title, "url": a.url, "date": a.published.isoformat()}
                    for a in used
                ),
                key=lambda s: s["date"],
                reverse=True,
            )
            entry = {
                "headline": headline,
                "summary": summary,
                "date": sources[0]["date"],
                "sources": sources,
            }
            if item.importance is not None:
                entry["importance"] = max(1, min(10, item.importance))
            if n1 + n2:
                entry["links_removed"] = n1 + n2
            sections[section.key].append(entry)

    out = []
    for key, title in names.items():
        items = sorted(sections[key], key=lambda i: i["date"], reverse=True)
        for extra in items[MAX_ITEMS_PER_SECTION:]:
            removed.append({"headline": extra["headline"], "reason": "section full"})
        out.append({"key": key, "title": title, "items": items[:MAX_ITEMS_PER_SECTION]})
    return {"sections": out, "removed": removed}


TOP_N = 5


def top_stories(sections: list[dict], n: int = TOP_N) -> list[dict]:
    """The day's top stories across sections: the most important first (the news agent's rating), newest first
    among equals. Older digests have no ratings: then each section's top item in turn."""
    items = [{**item, "section": sec["title"]} for sec in sections for item in sec["items"]]
    if any("importance" in i for i in items):
        items.sort(key=lambda i: (i.get("importance", 0), i["date"]), reverse=True)
        return items[:n]
    picked: list[dict] = []
    for rank in range(MAX_ITEMS_PER_SECTION):
        for sec in sections:
            if rank < len(sec["items"]) and len(picked) < n:
                picked.append({**sec["items"][rank], "section": sec["title"]})
    return picked


def keep_official_links(text: str, sites: list[str] | tuple[str, ...]) -> tuple[str, int]:
    """In an answer, keep links only to official sites; others are removed (their text stays)."""
    removed = 0

    def ok(url: str) -> bool:
        host = site_of(url)
        return urlsplit(url).scheme in ("http", "https") and any(host == s or host.endswith("." + s) for s in sites)

    def md(m: re.Match) -> str:
        nonlocal removed
        if ok(m.group(2)):
            return m.group(0)
        removed += 1
        return m.group(1)

    text = _MD_LINK.sub(md, text)

    def bare(m: re.Match) -> str:
        nonlocal removed
        url = m.group(0).rstrip(".,;:!?)")
        tail = m.group(0)[len(url) :]
        if url.lower().startswith("www."):
            url_full = "https://" + url
        else:
            url_full = url
        if ok(url_full):
            return m.group(0)
        removed += 1
        return tail

    # Bare links that aren't inside a markdown link we kept.
    parts = re.split(r"(\[[^\]]+\]\([^)]+\))", text)
    text = "".join(p if p.startswith("[") and "](" in p else _URL.sub(bare, p) for p in parts)
    return re.sub(r"[ \t]{2,}", " ", text), removed
