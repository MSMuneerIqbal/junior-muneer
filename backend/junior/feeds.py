"""Your own feeds (P7-05): news sites and blogs you follow, by RSS or Atom.

    GET    /api/feeds               your feeds
    POST   /api/feeds  {url}        add one (read once first, to check it's a real feed)
    DELETE /api/feeds/{id}          remove it and its items
    POST   /api/feeds/refresh       read them all now
    GET    /api/feeds/items         the newest items from all of them

They're read every 3 hours with the same safe reader as the news (plain HTTP, no browser,
redirects only within the feed's own site, 4 MB limit). No AI is used to read them. Their
items are outside content: data, never instructions.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from junior.audit import audit
from junior.config import get_settings
from junior.db import Feed, FeedItem, session_scope
from junior.db.models import utcnow
from junior.news.reader import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    ReadError,
    _local,
    _text,
    _xml_root,
    download,
    parse_feed,
)
from junior.news.sources import Source, site_of
from junior.settings_store import get_setting, set_setting

log = logging.getLogger(__name__)
router = APIRouter()
MAX_FEEDS = 30
KEEP_DAYS = 30
KEEP_PER_FEED = 50
EVERY = timedelta(hours=3)
NOT_A_FEED = (
    "That address isn't an RSS or Atom feed. Most blogs and news sites have one: look for “RSS” on the site, "
    "or try the address with /feed or /rss at the end."
)


class FeedError(ValueError):
    pass


class FeedOut(BaseModel):
    id: int
    url: str
    title: str
    item_count: int
    last_read_at: datetime | None
    last_error: str
    created_at: datetime


class ItemOut(BaseModel):
    id: int
    feed_id: int
    feed: str
    title: str
    url: str
    published_at: datetime | None
    summary: str


class FeedIn(BaseModel):
    url: str = Field(min_length=10, max_length=500)


def _transport(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncBaseTransport | None:
    if transport is None and get_settings().fake_ai:
        from junior.news.fake import sample_transport

        return sample_transport()  # FAKE_AI: sample feeds, no network
    return transport


def _client(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"},
        transport=_transport(transport),
    )


def feed_title(body: bytes) -> str:
    """The feed's own name (<channel><title> or Atom <title>)."""
    root = _xml_root(body)
    channel = next((e for e in root.iter() if _local(e.tag) == "channel"), root)
    title = next((e for e in channel if _local(e.tag) == "title"), None)
    return " ".join(_text(title).split())[:120] if title is not None else ""


async def read_feed(client: httpx.AsyncClient, url: str) -> tuple[str, list]:
    """(the feed's title, its items). Raises FeedError in plain words."""
    source = Source(name=site_of(url), topic="feeds", kind="rss", url=url)
    try:
        _, body = await download(client, url, source)
        items = parse_feed(body, source)
        title = feed_title(body)
    except ReadError as e:
        raise FeedError(NOT_A_FEED if "valid RSS" in str(e) else f"Couldn't read it: {e}.") from None
    except httpx.HTTPError:
        raise FeedError("Couldn't reach that address. Check it and the internet connection.") from None
    if not items and not title:
        raise FeedError(NOT_A_FEED)
    return title, [i for i in items if i.title and i.url.startswith(("https://", "http://"))]


def _save_items(s, feed: Feed, items: list, now: datetime) -> None:
    existing = {i.url: i for i in s.scalars(select(FeedItem).where(FeedItem.feed_id == feed.id))}
    for a in items:
        row = existing.get(a.url)
        if row is None:
            row = FeedItem(feed_id=feed.id, url=a.url[:500])
            s.add(row)
            existing[a.url] = row
        row.title, row.summary = a.title[:300], a.summary
        row.published_at = a.published if a.published.year > 1900 else None
        row.fetched_at = now
    s.flush()
    # Keep the newest items of the last 30 days.
    rows = sorted(existing.values(), key=lambda r: r.published_at or r.fetched_at, reverse=True)
    cutoff = now - timedelta(days=KEEP_DAYS)
    for n, row in enumerate(rows):
        if n >= KEEP_PER_FEED or (row.published_at and _aware(row.published_at) < cutoff):
            s.delete(row)
    feed.item_count = min(len(rows), KEEP_PER_FEED)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _out(f: Feed) -> FeedOut:
    return FeedOut(id=f.id, url=f.url, title=f.title, item_count=f.item_count, last_read_at=f.last_read_at,
                   last_error=f.last_error, created_at=f.created_at)


async def add_feed(url: str, transport: httpx.AsyncBaseTransport | None = None) -> FeedOut:
    url = url.strip()
    if urlsplit(url).scheme not in ("https", "http") or not urlsplit(url).netloc:
        raise FeedError("Give the feed's full address, starting with https://")
    with session_scope() as s:
        if s.scalars(select(Feed).where(Feed.url == url)).first():
            raise FeedError("You already follow that feed.")
        if len(s.scalars(select(Feed.id)).all()) >= MAX_FEEDS:
            raise FeedError(f"You can follow up to {MAX_FEEDS} feeds. Remove one first.")
    async with _client(transport) as client:
        title, items = await read_feed(client, url)
    now = utcnow()
    with session_scope() as s:
        feed = Feed(url=url, title=title or site_of(url), last_read_at=now, last_error="", item_count=0)
        s.add(feed)
        s.flush()
        _save_items(s, feed, items, now)
        out = _out(feed)
    audit("action", "feed_added", detail={"url": url, "title": out.title, "items": out.item_count})
    return out


async def refresh_feeds(transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Read every feed now. A broken feed never stops the others; its error is kept on it."""
    with session_scope() as s:
        feeds = [(f.id, f.url) for f in s.scalars(select(Feed))]
    if not feeds:
        return {"read": 0, "failed": 0}
    async with _client(transport) as client:

        async def one(url: str):
            try:
                return await asyncio.wait_for(read_feed(client, url), 60), ""
            except FeedError as e:
                return None, str(e)
            except TimeoutError:
                return None, "It took too long to answer."

        results = await asyncio.gather(*(one(url) for _, url in feeds))
    now = utcnow()
    failed = 0
    with session_scope() as s:
        for (feed_id, _), (got, error) in zip(feeds, results):
            feed = s.get(Feed, feed_id)
            if feed is None:
                continue
            feed.last_read_at, feed.last_error = now, error
            if got is None:
                failed += 1
                continue
            title, items = got
            feed.title = title or feed.title
            _save_items(s, feed, items, now)
    set_setting("feeds_read_at", now.isoformat())
    return {"read": len(feeds) - failed, "failed": failed}


def latest_items(days: int = 7, limit: int = 30) -> list[ItemOut]:
    since = utcnow() - timedelta(days=days)
    with session_scope() as s:
        rows = s.execute(
            select(FeedItem, Feed.title)
            .join(Feed, Feed.id == FeedItem.feed_id)
            .where((FeedItem.published_at >= since) | (FeedItem.published_at.is_(None) & (FeedItem.fetched_at >= since)))
            .order_by(FeedItem.published_at.desc().nulls_last(), FeedItem.id.desc())
            .limit(limit)
        ).all()
        return [ItemOut(id=i.id, feed_id=i.feed_id, feed=t, title=i.title, url=i.url, published_at=i.published_at, summary=i.summary) for i, t in rows]


async def feeds_if_due() -> None:
    """Scheduler job: read your feeds every 3 hours (not while paused)."""
    from junior.pause import is_paused

    if is_paused():
        return
    last = get_setting("feeds_read_at") or ""
    try:
        if last and datetime.now(UTC) - datetime.fromisoformat(last) < EVERY:
            return
    except ValueError:
        pass
    try:
        await refresh_feeds()
    except Exception:
        log.exception("Reading your feeds failed; will try again later")


# ---- API --------------------------------------------------------------------


@router.get("/api/feeds", response_model=list[FeedOut])
def list_feeds() -> list[FeedOut]:
    with session_scope() as s:
        return [_out(f) for f in s.scalars(select(Feed).order_by(Feed.title))]


@router.post("/api/feeds", response_model=FeedOut, status_code=201)
async def create_feed(body: FeedIn) -> FeedOut:
    try:
        return await add_feed(body.url)
    except FeedError as e:
        raise HTTPException(422, str(e)) from None


@router.delete("/api/feeds/{feed_id}", status_code=204)
def remove_feed(feed_id: int) -> None:
    with session_scope() as s:
        feed = s.get(Feed, feed_id)
        if feed is None:
            raise HTTPException(404, f"Feed {feed_id} not found")
        url = feed.url
        s.execute(delete(FeedItem).where(FeedItem.feed_id == feed_id))
        s.delete(feed)
    audit("action", "feed_removed", detail={"url": url})


@router.post("/api/feeds/refresh")
async def refresh_now() -> dict:
    return await refresh_feeds()


@router.get("/api/feeds/items", response_model=list[ItemOut])
def items(days: int = 7, limit: int = 30) -> list[ItemOut]:
    return latest_items(max(1, min(days, 30)), max(1, min(limit, 100)))
