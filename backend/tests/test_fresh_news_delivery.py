"""72-hour publication evidence and restart-safe no-repeat daily delivery."""
import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from junior.agent.context import TurnContext
from junior.db import NewsDigest, session_scope
from junior.db.models import NewsDelivery
from junior.main import create_app
from junior.news.digest import latest_digest
from junior.news.discovery import discover_news
from junior.news.reader import fetch_topic
from junior.news.sources import Source
from junior.news import mail
from junior.settings_store import all_settings
from test_news_email import gmail

NOW = datetime.now(UTC).replace(microsecond=0)
SOURCE = Source("OpenAI", "ai", "rss", "https://openai.com/news/rss.xml")


def item(name, date=NOW):
    return {"headline": name, "summary": "Verified update.", "date": date.isoformat(), "importance": 9,
        "sources": [{"title": name, "name": "OpenAI", "url": f"https://openai.com/index/{name}", "date": date.isoformat()}]}


def add(items, built=None):
    with session_scope() as s:
        row = NewsDigest(topic="ai", built_at=built or NOW, data={"topic": "ai", "label": "AI", "window_days": 15,
            "sections": [{"key": "models", "title": "Models", "items": items}], "top": [item("Cached-old", NOW-timedelta(days=10))]})
        s.add(row); s.flush(); return row.id


def test_reader_72_hour_boundary_future_and_updated_only_dates():
    entries = []
    for name, when in (("Boundary", NOW-timedelta(days=3)), ("Old", NOW-timedelta(days=3, seconds=1)), ("Future", NOW+timedelta(seconds=1))):
        entries.append(f"<item><title>{name}</title><link>https://openai.com/{name}</link><pubDate>{format_datetime(when)}</pubDate></item>")
    entries.append(f"<entry><title>Updated only</title><link>https://openai.com/updated</link><updated>{NOW.isoformat()}</updated></entry>")
    body = "<rss><channel>" + "".join(entries) + "</channel></rss>"
    result = asyncio.run(fetch_topic("ai", [SOURCE], now=NOW, transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))))
    assert [a.title for a in result.articles] == ["Boundary"]


def test_modification_times_and_dates_in_body_are_not_publication_evidence():
    from junior.news.reader import article_details
    for tag in ('<time datetime="2026-10-26">Updated today</time>', '<time itemprop="dateModified" datetime="2026-10-26">Updated</time>'):
        assert article_details(tag + "Original announcement mentioned October 26, 2026.", "", SOURCE)[1] is None
    assert article_details('<time itemprop="datePublished" datetime="2026-10-26T10:00:00Z">Published</time>', "", SOURCE)[1] == datetime(2026,10,26,10,tzinfo=UTC)


def test_ainews_google_feed_checks_publisher_and_keeps_only_its_verified_article_links():
    from junior.news.sources import load_sources, official_sites
    from junior.news.guard import keep_official_links
    source = next(s for s in load_sources() if s.name == "AI News (ainews.com)")
    assert source.publisher_domain == "ainews.com"
    assert "ainews.com" in official_sites("ai") and "news.google.com" not in official_sites("ai")
    good = "https://news.google.com/rss/articles/good"
    bad = "https://news.google.com/rss/articles/other"
    body = f'<rss><channel><item><title>Fresh AI News story</title><link>{good}</link><pubDate>{format_datetime(NOW)}</pubDate><source url="https://www.ainews.com">AI News</source></item><item><title>Wrong publisher</title><link>{bad}</link><pubDate>{format_datetime(NOW)}</pubDate><source url="https://evil.example">Other</source></item></channel></rss>'
    result = asyncio.run(fetch_topic("ai", [source], now=NOW, transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))))
    assert [a.url for a in result.articles] == [good]
    text, removed = keep_official_links(f"Verified {good} unverified {bad}", official_sites("ai"), {good})
    assert good in text and bad not in text and removed == 1


def test_old_saved_digest_and_cached_top_are_filtered_at_read_time():
    add([item("Recent", NOW-timedelta(days=1)), item("Old", NOW-timedelta(days=4)), item("Future", NOW+timedelta(days=1))])
    result = latest_digest("ai", now=NOW)
    assert result["window_days"] == 3 and [i["headline"] for i in result["top"]] == ["Recent"]
    with TestClient(create_app()) as c:
        assert [i["headline"] for i in c.get("/api/news/ai").json()["digest"]["top"]] == ["Recent"]


def test_repeat_stories_are_not_emailed_again_after_restart_but_new_stories_are(gmail):
    c, sent = gmail
    add([item("First")])
    assert c.post("/api/news-email/send").status_code == 200
    add([item("First"), item("Second")], NOW+timedelta(seconds=1))
    with TestClient(create_app()) as restarted:
        assert restarted.post("/api/news-email/send").status_code == 200
        assert restarted.post("/api/news-email/send").status_code == 400
    assert len(sent) == 2
    assert "Second" in sent[1].get_body(("plain",)).get_content()
    assert "First" not in sent[1].get_body(("plain",)).get_content()


def test_old_or_uncertain_news_is_never_retried_automatically(gmail, monkeypatch):
    c, sent = gmail
    add([item("Stale", NOW-timedelta(days=4))])
    assert c.post("/api/news-email/send").status_code == 400 and not sent
    add([item("Pending")], NOW+timedelta(seconds=1))
    calls = []
    async def uncertain(*args):
        calls.append(1)
        raise mail.MailError("SMTP did not confirm delivery")
    monkeypatch.setattr(mail, "send_to_self", uncertain)
    assert c.post("/api/news-email/send").status_code == 400
    assert c.post("/api/news-email/send").status_code == 400 and len(calls) == 1
    with session_scope() as s:
        assert {d.state for d in s.scalars(select(NewsDelivery))} == {"unclear"}


def test_google_grounding_candidates_require_official_fetched_publication_evidence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from junior.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr("junior.news.discovery.official_sites", lambda topic: ["openai.com"])
    queries = []
    async def search(query, context):
        queries.append(query)
        context.research_sources.update({
            "https://vertexaisearch.cloud.google.com/grounding-api-redirect/new": "New",
            "https://openai.com/old": "Old", "https://openai.com/undated": "Undated", "https://openai.com/future": "Future",
            "https://evil.example/private": "Offsite"})
        return "A search summary must never become a dated article."
    monkeypatch.setattr("junior.news.discovery.gemini_search", search)
    seen = []
    def route(request):
        seen.append(str(request.url))
        if request.url.host == "vertexaisearch.cloud.google.com":
            return httpx.Response(302, headers={"location": "https://openai.com/new"})
        date = NOW-timedelta(hours=1) if request.url.path == "/new" else NOW-timedelta(days=4) if request.url.path == "/old" else NOW+timedelta(days=1)
        pub = "" if request.url.path == "/undated" else f'<meta property="article:published_time" content="{date.isoformat()}">'
        return httpx.Response(200, text=f'<title>Verified release</title>{pub}<meta name="description" content="Official new release."><time>{NOW.isoformat()}</time>')
    context = TurnContext(conversation_id=None, settings=all_settings())
    found, error = asyncio.run(discover_news("ai", context, NOW, [SOURCE], transport=httpx.MockTransport(route)))
    assert error is None and [a.url for a in found] == ["https://openai.com/new"]
    assert "after:" in queries[0] and "before:" in queries[0]
    assert not any("evil.example" in url for url in seen)


def test_upgrade_seeds_previous_deliveries_instead_of_resending_old_news(gmail):
    c, sent = gmail
    from alembic import command
    from junior.db.engine import alembic_config, close_all_connections
    from junior.settings_store import set_setting
    from junior.news.delivery import claim
    add([item("Already emailed")])
    set_setting("news_emailed_on", NOW.date().isoformat())
    close_all_connections()
    command.downgrade(alembic_config(), "f8d0e2a4b6c9")
    command.upgrade(alembic_config(), "head")
    _, selected = claim(latest_digest("ai", now=NOW))
    assert selected == [] and not sent
