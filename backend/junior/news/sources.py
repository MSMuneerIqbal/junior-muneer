"""The official news sources (news/sources.toml): the only things the news agents read."""

import tomllib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from junior.config import REPO_DIR

SOURCES_FILE = REPO_DIR / "news" / "sources.toml"
TOPICS = ("ai", "pakistan")
KINDS = ("rss", "page", "trends")
_FIELDS = {"name", "topic", "kind", "url", "domains", "link_prefix", "keywords", "max_items"}
MAX_SEARCH_SITES = 20  # the web search filter's limit


class NewsSourceError(Exception):
    """news/sources.toml is broken. The message names the source and the problem."""


def site_of(url: str) -> str:
    """The site of a link, without "www.", e.g. "dawn.com"."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


@dataclass(frozen=True)
class Source:
    name: str
    topic: str
    kind: str
    url: str
    domains: tuple[str, ...] = ()
    link_prefix: str = ""
    keywords: tuple[str, ...] = ()
    max_items: int = 30

    @property
    def publisher_domain(self) -> str:
        """Google News RSS is restricted to the publisher explicitly requested in its site: query."""
        parts = urlsplit(self.url)
        if site_of(self.url) == "news.google.com" and parts.path == "/rss/search":
            query = parse_qs(parts.query).get("q", [""])[0]
            match = re.search(r"(?:^|\s)site:([a-zA-Z0-9.-]+)", query)
            return match.group(1).casefold().removeprefix("www.") if match else ""
        return ""

    @property
    def sites(self) -> tuple[str, ...]:
        """Sites this source's articles may live on: its own, plus `domains`."""
        return (site_of(self.url), *(d.lower().removeprefix("www.") for d in self.domains))

    def allows(self, url: str) -> bool:
        """True if a link is on one of this source's sites (https or http only)."""
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http"):
            return False
        host = site_of(url)
        return any(host == s or host.endswith("." + s) for s in self.sites)


def load_sources(path: Path | None = None) -> list[Source]:
    """Read and check every source. A broken file stops startup with a clear error."""
    path = path or SOURCES_FILE
    if not path.exists():
        raise NewsSourceError(f"{path} is missing.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise NewsSourceError(f"news/sources.toml is not valid TOML: {e}") from None
    raw = data.get("source")
    if not isinstance(raw, list) or not raw:
        raise NewsSourceError("news/sources.toml has no [[source]] entries.")

    sources: list[Source] = []
    names: set[str] = set()
    for n, entry in enumerate(raw, start=1):
        label = f"news/sources.toml, source {n}" + (f" ({entry.get('name')})" if entry.get("name") else "")

        def fail(msg: str) -> NewsSourceError:
            return NewsSourceError(f"{label}: {msg}")

        unknown = set(entry) - _FIELDS
        if unknown:
            raise fail(f"unknown field(s) {sorted(unknown)}; allowed: {sorted(_FIELDS)}.")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise fail("'name' is required.")
        if name in names:
            raise fail(f"the name {name!r} is used twice.")
        names.add(name)
        topic, kind, url = entry.get("topic"), entry.get("kind"), entry.get("url")
        if topic not in TOPICS:
            raise fail(f"'topic' must be one of {list(TOPICS)}.")
        if kind not in KINDS:
            raise fail(f"'kind' must be one of {list(KINDS)}.")
        if not isinstance(url, str) or urlsplit(url).scheme != "https" or not site_of(url):
            raise fail("'url' must be a full https:// address.")

        def str_list(key: str) -> tuple[str, ...]:
            value = entry.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                raise fail(f"'{key}' must be a list of words, e.g. {key} = [\"a\", \"b\"].")
            return tuple(v.strip() for v in value)

        link_prefix = entry.get("link_prefix", "")
        if kind == "page" and (not isinstance(link_prefix, str) or not link_prefix.startswith("/")):
            raise fail("a 'page' source needs 'link_prefix', the path articles start with, e.g. \"/news/\".")
        max_items = entry.get("max_items", 30)
        if not isinstance(max_items, int) or isinstance(max_items, bool) or not 1 <= max_items <= 200:
            raise fail("'max_items' must be a whole number from 1 to 200.")
        sources.append(
            Source(
                name=name.strip(),
                topic=topic,
                kind=kind,
                url=url,
                domains=str_list("domains"),
                link_prefix=link_prefix,
                keywords=str_list("keywords"),
                max_items=max_items,
            )
        )
    return sources


def official_sites(topic: str, path: Path | None = None) -> list[str]:
    """Every official site for a topic: the sources' own sites plus [search] extras (for web search
    and for checking the links in answers)."""
    path = path or SOURCES_FILE
    sites: list[str] = []
    for s in load_sources(path):
        if s.topic == topic:
            sites.extend((s.publisher_domain, *s.domains) if s.publisher_domain else s.sites)
    extra = tomllib.loads(path.read_text(encoding="utf-8")).get("search", {}).get(topic, [])
    if not isinstance(extra, list) or not all(isinstance(e, str) for e in extra):
        raise NewsSourceError(f"news/sources.toml: [search] {topic} must be a list of sites.")
    sites.extend(e.lower().removeprefix("www.") for e in extra)
    unique = list(dict.fromkeys(sites))
    # "news.microsoft.com" is already covered by "microsoft.com".
    return [s for s in unique if not any(s != p and s.endswith("." + p) for p in unique)]


def sources_for(topic: str, sources: list[Source] | None = None) -> list[Source]:
    return [s for s in (sources if sources is not None else load_sources()) if s.topic == topic]
