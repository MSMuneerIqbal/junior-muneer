"""Reads the official news sources with plain HTTP (P2b-01).

RSS and Atom feeds, news pages and Google Trends, read the way a feed reader does: one request per
feed or page (and per article on news pages), no browser, no logins, no cookies, and a time and
size limit on everything. Only links on a source's own sites are kept, redirects to any other site
are refused, and only the last 15 days are kept, newest first, without duplicates.

Everything read here is outside content: data, never instructions.
"""

import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from junior.news.sources import Source, site_of

log = logging.getLogger(__name__)

WINDOW_DAYS = 15
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 20
SOURCE_SECONDS = 90  # a whole source, including its article pages
MAX_REDIRECTS = 4
MAX_PAGE_ARTICLES = 8  # articles opened per news page
PARALLEL = 6
SUMMARY_CHARS = 500
TITLE_CHARS = 200
USER_AGENT = "JuniorMuneer/0.1 (personal news reader; +https://github.com/MSMuneerIqbal/junior-muneer)"


class ReadError(Exception):
    """A source couldn't be read. The message is short and plain."""


@dataclass
class Article:
    source: str
    topic: str
    title: str
    url: str
    published: datetime
    summary: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    topic: str
    articles: list[Article]
    failed: list[dict]  # {"source": name, "reason": "..."}
    read: list[str]  # sources read fine
    dropped: int = 0  # items left out: too old, undated, off-site or duplicates


# ---- dates ---------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
_LONG_DATE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}),? (20\d\d)\b", re.IGNORECASE
)
_NUM_DATE = re.compile(r"\b(20\d\d)[/-](\d{1,2})[/-](\d{1,2})\b")


def find_date(text: str) -> datetime | None:
    """A date written in text: "Oct 15, 2026", "October 6, 2026", "2026/09/10" or "2026-09-10"."""
    m = _LONG_DATE.search(text)
    if m:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), tzinfo=UTC)
        except ValueError:
            pass
    m = _NUM_DATE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=UTC)
        except ValueError:
            pass
    return None


def parse_date(text: str | None) -> datetime | None:
    """RSS (RFC 2822), Atom and meta-tag (ISO 8601) dates, or a date written in text."""
    if not text or not text.strip():
        return None
    t = text.strip()
    try:  # RFC 2822; some feeds write the offset as "+05:00"
        d = parsedate_to_datetime(re.sub(r"([+-]\d\d):(\d\d)$", r"\1\2", t))
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return find_date(t)


# ---- text ----------------------------------------------------------------------


def clean_text(fragment: str | None, limit: int = SUMMARY_CHARS) -> str:
    """Plain text from a bit of HTML (feeds often escape their HTML twice)."""
    if not fragment:
        return ""
    text = html.unescape(fragment)
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def _clean_title(title: str, source: Source) -> str:
    """Drop a site-name tail like " | DeepSeek API Docs" or " - Arena.ai"."""
    title = clean_text(title, TITLE_CHARS)
    root = site_of(source.url).split(".")[-2] if "." in site_of(source.url) else ""
    m = re.match(r"^(.*\S)\s+[|–—-]\s+([^|–—-]{2,60})$", title)
    if m and (root and root in m.group(2).lower() or source.name.split()[0].lower() in m.group(2).lower()):
        return m.group(1)
    return title


def normalize_url(url: str) -> str:
    """For finding duplicates: no www, no tracking parameters, no trailing slash."""
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    keep_fragment = site_of(url) == "trends.google.com"  # a trend's fragment is the trend itself
    return urlunsplit(
        (
            parts.scheme.lower(),
            site_of(url),
            parts.path.rstrip("/") or "/",
            query,
            parts.fragment if keep_fragment else "",
        )
    )


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", title.lower())


# ---- feeds ---------------------------------------------------------------------


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _child(item: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        for c in item:
            if _local(c.tag) == name:
                return c
    return None


def _feed_link(item: ET.Element) -> str:
    for c in item:
        if _local(c.tag) != "link":
            continue
        href = c.get("href")
        if href and c.get("rel", "alternate") == "alternate":
            return href.strip()
        if not href and _text(c):
            return _text(c)
    guid = _child(item, "guid", "id")
    if guid is not None and _text(guid).startswith("http"):
        return _text(guid)
    return ""


def _xml_root(body: bytes) -> ET.Element:
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        raise ReadError("the feed isn't valid RSS or Atom") from None


def parse_feed(body: bytes, source: Source) -> list[Article]:
    items = [e for e in _xml_root(body).iter() if _local(e.tag) in ("item", "entry")]
    out = []
    for item in items:
        out.append(
            Article(
                source=source.name,
                topic=source.topic,
                title=_clean_title(_text(_child(item, "title")), source),
                url=_feed_link(item),
                published=parse_date(_text(_child(item, "pubDate", "published", "date", "updated")))
                or datetime.min.replace(tzinfo=UTC),
                summary=clean_text(_text(_child(item, "description", "summary", "encoded", "content"))),
            )
        )
    return out


def parse_trends(body: bytes, source: Source) -> list[Article]:
    """Google Trends: each trending search, its traffic and the headlines Google shows for it."""
    geo = dict(parse_qsl(urlsplit(source.url).query)).get("geo", "PK")
    out = []
    for item in (e for e in _xml_root(body).iter() if _local(e.tag) == "item"):
        term = clean_text(_text(_child(item, "title")), TITLE_CHARS)
        if not term:
            continue
        traffic = _text(_child(item, "approx_traffic"))
        related = []
        for news in (c for c in item if _local(c.tag) == "news_item"):
            headline = clean_text(_text(_child(news, "news_item_title")), TITLE_CHARS)
            if headline:
                related.append({"title": headline, "source": clean_text(_text(_child(news, "news_item_source")), 60)})
        summary = f"Searches: {traffic}." if traffic else ""
        if related:
            summary += f" Google Trends links it to: \"{related[0]['title']}\" ({related[0]['source']})."
        out.append(
            Article(
                source=source.name,
                topic=source.topic,
                title=term,
                url=f"https://trends.google.com/trending?geo={geo}#{quote(term)}",
                published=parse_date(_text(_child(item, "pubDate"))) or datetime.min.replace(tzinfo=UTC),
                summary=summary.strip(),
                extra={"traffic": traffic, "related": related[:3]},
            )
        )
    return out


# ---- news pages -------------------------------------------------------------------


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", " ".join(self._text)).strip()))
            self._href = None


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.times: list[str] = []
        self.title = ""
        self._in: str | None = None
        self.ld_json: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "title":
            self._in = "title"
        elif tag == "script":
            self._in = "ld" if a.get("type") == "application/ld+json" else "script"
        elif tag == "style":
            self._in = "script"

    def handle_endtag(self, tag):
        if tag in ("title", "script", "style"):
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "ld":
            self.ld_json.append(data)
        elif self._in is None and sum(len(t) for t in self.text) < 60_000:
            self.text.append(data)


def page_article_links(page: str, base_url: str, source: Source) -> list[tuple[str, str]]:
    """The article links on a news page: on the source's site, under its link prefix, in page order."""
    parser = _Links()
    parser.feed(page)
    found: dict[str, tuple[str, str]] = {}  # normalized url -> (url, link text), in page order
    for href, text in parser.links:
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        path = urlsplit(url).path
        if (
            not source.allows(url)
            or not path.startswith(source.link_prefix)
            or path.rstrip("/") == source.link_prefix.rstrip("/")
            or re.search(r"/(category|tag|tags|page|author|rss|feed)(/|$)", path)
        ):
            continue
        key = normalize_url(url)
        # The same article is often linked twice (picture and title): keep the text with a date.
        if key not in found or (find_date(text) and not find_date(found[key][1])):
            found[key] = (found[key][0] if key in found else url, text)
    return list(found.values())


def article_details(page: str, link_text: str, source: Source) -> tuple[str, datetime | None, str]:
    """Title, publish date and description of one article page."""
    m = _Meta()
    m.feed(page)
    title = m.meta.get("og:title") or m.title or re.sub(_LONG_DATE, "", link_text)
    date = parse_date(m.meta.get("article:published_time") or m.meta.get("datepublished"))
    if date is None:
        ld = re.search(r'"datePublished"\s*:\s*"([^"]+)"', " ".join(m.ld_json))
        date = parse_date(ld.group(1)) if ld else None
    if date is None and m.times:
        date = parse_date(m.times[0])
    if date is None:
        date = find_date(link_text) or find_date(" ".join(m.text))
    description = m.meta.get("og:description") or m.meta.get("description") or ""
    return _clean_title(title, source), date, clean_text(description)


# ---- downloading ----------------------------------------------------------------


async def download(client: httpx.AsyncClient, url: str, source: Source) -> tuple[str, bytes]:
    """GET one address. Redirects are followed only within the source's own sites."""
    for _ in range(MAX_REDIRECTS + 1):
        if not source.allows(url):
            raise ReadError(f"refused a redirect to another site ({site_of(url)})")
        async with client.stream("GET", url) as r:
            if r.is_redirect:
                url = urljoin(url, r.headers.get("location", ""))
                continue
            if r.status_code != 200:
                raise ReadError(f"the site answered {r.status_code}")
            chunks, total = [], 0
            async for chunk in r.aiter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ReadError("it's too big (over 4 MB)")
                chunks.append(chunk)
            return str(r.url), b"".join(chunks)
    raise ReadError("too many redirects")


def _decode(body: bytes) -> str:
    m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', body[:2048], re.IGNORECASE)
    try:
        return body.decode(m.group(1).decode() if m else "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def read_source(client: httpx.AsyncClient, source: Source) -> list[Article]:
    final_url, body = await download(client, source.url, source)
    if source.kind == "rss":
        return parse_feed(body, source)
    if source.kind == "trends":
        return parse_trends(body, source)
    links = page_article_links(_decode(body), final_url, source)[:MAX_PAGE_ARTICLES]

    async def one(url: str, text: str) -> Article | None:
        try:
            _, page = await download(client, url, source)
        except (ReadError, httpx.HTTPError):
            return None
        title, date, description = article_details(_decode(page), text, source)
        if not title or date is None:
            return None
        return Article(source.name, source.topic, title, url, date, description)

    found = await asyncio.gather(*(one(u, t) for u, t in links))
    return [a for a in found if a is not None]


def _mentions(article: Article, keywords: tuple[str, ...]) -> bool:
    text = f"{article.title} {article.summary}"
    return any(re.search(rf"\b{re.escape(k)}\b", text, re.IGNORECASE) for k in keywords)


def _why(e: BaseException) -> str:
    if isinstance(e, ReadError):
        return str(e)
    if isinstance(e, (TimeoutError, httpx.TimeoutException)):
        return "it timed out"
    if isinstance(e, httpx.HTTPError):
        return "couldn't connect"
    return "couldn't be read"


async def fetch_topic(
    topic: str,
    sources: list[Source],
    *,
    now: datetime | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """Read every source for a topic: articles from the last 15 days, newest first, no duplicates."""
    now = now or datetime.now(UTC)
    oldest, newest = now - timedelta(days=WINDOW_DAYS), now + timedelta(days=1)
    chosen = [s for s in sources if s.topic == topic]
    limit = asyncio.Semaphore(PARALLEL)
    dropped = 0

    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/html;q=0.9, */*;q=0.5"},
        transport=transport,
    ) as client:

        async def one(source: Source):
            async with limit:
                try:
                    return source, await asyncio.wait_for(read_source(client, source), SOURCE_SECONDS), None
                except Exception as e:  # one broken source never stops the others
                    if not isinstance(e, (ReadError, TimeoutError, httpx.HTTPError)):
                        log.exception("News source %s failed", source.name)
                    return source, [], _why(e)

        results = await asyncio.gather(*(one(s) for s in chosen))

    articles: list[Article] = []
    failed, read = [], []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for source, items, error in results:
        if error:
            failed.append({"source": source.name, "reason": error})
            continue
        read.append(source.name)
        kept = []
        for a in items:
            if (
                not a.title
                or not source.allows(a.url)
                or not oldest <= a.published <= newest
                or (source.keywords and not _mentions(a, source.keywords))
            ):
                dropped += 1
                continue
            kept.append(a)
        kept.sort(key=lambda a: a.published, reverse=True)
        for a in kept[: source.max_items]:
            url_key, title_key = normalize_url(a.url), _title_key(a.title)
            if url_key in seen_urls or title_key in seen_titles:
                dropped += 1
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            articles.append(a)
        dropped += max(0, len(kept) - source.max_items)
    articles.sort(key=lambda a: a.published, reverse=True)
    return FetchResult(topic=topic, articles=articles, failed=failed, read=read, dropped=dropped)
