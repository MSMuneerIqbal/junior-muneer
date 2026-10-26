"""P2b-01: the official news sources and the plain-HTTP reader. No internet: saved sample feeds."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from junior.news import sources as sources_module
from junior.news.reader import MAX_BYTES, fetch_topic, normalize_url, parse_date
from junior.news.sources import NewsSourceError, Source, load_sources

DATA = Path(__file__).parent / "data" / "news"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def sample(name: str) -> bytes:
    return (DATA / name).read_bytes()


def serve(routes: dict[str, object]) -> httpx.MockTransport:
    """A fake internet: url -> body (bytes), (status, headers) or an exception to raise."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        assert "cookie" not in request.headers  # no logins, no cookies
        assert request.headers["user-agent"].startswith("JuniorMuneer/")
        answer = routes.get(url)
        if answer is None:
            return httpx.Response(404, text="not found")
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, tuple):
            status, headers = answer
            return httpx.Response(status, headers=headers)
        return httpx.Response(200, content=answer)

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


def fetch(topic, sources, routes):
    transport = serve(routes)
    result = asyncio.run(fetch_topic(topic, sources, now=NOW, transport=transport))
    return result, transport.seen  # type: ignore[attr-defined]


OPENAI = Source("OpenAI", "ai", "rss", "https://openai.com/news/rss.xml")
DEEPMIND = Source("Google DeepMind", "ai", "rss", "https://deepmind.google/blog/rss.xml")
ANTHROPIC = Source("Anthropic", "ai", "page", "https://www.anthropic.com/news", link_prefix="/news/")
GEO = Source("Geo News", "pakistan", "rss", "https://www.geo.tv/rss/1/1")
TRENDS = Source("Google Trends Pakistan", "pakistan", "trends", "https://trends.google.com/trending/rss?geo=PK")


# ---- the sources file ---------------------------------------------------------------


def test_the_real_sources_file_loads():
    sources = load_sources()
    assert {s.topic for s in sources} == {"ai", "pakistan"}
    names = {s.name for s in sources}
    assert {"OpenAI", "Anthropic", "Google DeepMind", "Dawn", "Google Trends Pakistan"} <= names
    assert all(s.url.startswith("https://") for s in sources)


GOOD = '[[source]]\nname = "OpenAI"\ntopic = "ai"\nkind = "rss"\nurl = "https://openai.com/news/rss.xml"\n'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("this is = not [toml", "not valid TOML"),
        ("title = 'no sources'", "has no [[source]] entries"),
        (GOOD.replace('topic = "ai"', 'topic = "sports"'), "'topic' must be one of"),
        (GOOD.replace('kind = "rss"', 'kind = "scrape"'), "'kind' must be one of"),
        (GOOD.replace("https://", "http://"), "full https:// address"),
        (GOOD + 'color = "blue"\n', "unknown field(s) ['color']"),
        (GOOD.replace('kind = "rss"', 'kind = "page"'), "needs 'link_prefix'"),
        (GOOD + GOOD, "used twice"),
        (GOOD + "max_items = 0\n", "'max_items' must be"),
        (GOOD + 'keywords = "AI"\n', "'keywords' must be a list"),
    ],
)
def test_a_broken_sources_file_gives_a_clear_error(tmp_path, text, message):
    path = tmp_path / "sources.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(NewsSourceError) as e:
        load_sources(path)
    assert "news/sources.toml" in str(e.value) and message in str(e.value)


def test_a_broken_sources_file_stops_startup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from junior.main import create_app

    broken = tmp_path / "sources.toml"
    broken.write_text(GOOD.replace('topic = "ai"', 'topic = "x"'), encoding="utf-8")
    monkeypatch.setattr(sources_module, "SOURCES_FILE", broken)
    with pytest.raises(NewsSourceError, match="'topic' must be one of"):
        with TestClient(create_app(model_provider=lambda: (lambda n: None))):
            pass


def test_sources_only_allow_their_own_sites():
    s = Source("Microsoft", "ai", "rss", "https://news.microsoft.com/source/feed/", domains=("microsoft.com",))
    assert s.allows("https://news.microsoft.com/source/a") and s.allows("https://blogs.microsoft.com/b")
    assert not s.allows("https://microsoft.com.evil.example/c")
    assert not s.allows("https://notmicrosoft.com/d")
    assert not s.allows("javascript:alert(1)") and not s.allows("ftp://microsoft.com/x")


# ---- reading feeds -----------------------------------------------------------------------


def test_rss_keeps_three_days_on_site_no_duplicates_newest_first():
    result, _ = fetch("ai", [OPENAI], {OPENAI.url: sample("openai_rss.xml")})
    assert result.failed == [] and result.read == ["OpenAI"]
    assert [a.title for a in result.articles] == ["Introducing GPT-7", "Codex for teams"]
    gpt = result.articles[0]
    assert gpt.url == "https://openai.com/index/introducing-gpt-7/"
    assert gpt.published == datetime(2026, 10, 14, 17, 0, tzinfo=UTC)
    assert gpt.summary == "GPT-7 scores 91.2% on SWE-bench Verified & is rolling out today."
    assert result.articles[1].published == datetime(2026, 10, 13, 8, 30, tzinfo=UTC)  # dc:date
    # Left out: the old story, the off-site link, the duplicate and the undated item.
    assert result.dropped == 4


def test_atom_and_rss_with_odd_dates():
    result, _ = fetch("ai", [DEEPMIND], {DEEPMIND.url: sample("deepmind_atom.xml")})
    [a] = result.articles
    assert a.title == "Gemini 4 Ultra & what it can do"
    assert a.url == "https://deepmind.google/blog/gemini-4-ultra/"  # the alternate link, not the image
    assert a.summary == "Gemini 4 Ultra leads on reasoning ."
    assert a.published == datetime(2026, 10, 13, 9, 0, tzinfo=UTC)

    result, _ = fetch("pakistan", [GEO], {GEO.url: sample("geo_rss.xml")})
    [g] = result.articles
    assert g.published == datetime(2026, 10, 15, 4, 11, tzinfo=UTC)  # "+05:00" understood
    assert g.summary == "The joint sitting approved it on Thursday."


def test_google_trends():
    result, _ = fetch("pakistan", [TRENDS], {TRENDS.url: sample("trends_pk.xml")})
    babar, petrol = result.articles
    assert babar.title == "babar azam" and babar.extra["traffic"] == "50K+"
    assert babar.url == "https://trends.google.com/trending?geo=PK#babar%20azam"
    assert 'Google Trends links it to: "Babar Azam named captain for the T20 series" (Dawn)' in babar.summary
    assert petrol.summary == "Searches: 20K+."


def test_news_pages_use_each_articles_own_date():
    routes = {
        ANTHROPIC.url: sample("anthropic_news.html"),
        "https://www.anthropic.com/news/claude-6": sample("anthropic_claude6.html"),
        "https://www.anthropic.com/news/safety-update": sample("anthropic_safety.html"),
    }
    result, seen = fetch("ai", [ANTHROPIC], routes)
    claude, safety = result.articles
    assert claude.title == "Introducing Claude 6"
    assert claude.published == datetime(2026, 10, 14, 16, 0, tzinfo=UTC)  # from the article's tags
    assert claude.summary.startswith("Claude 6 is our most capable model")
    assert safety.title == "A safety update"  # site name trimmed from the page title
    assert safety.published == datetime(2026, 10, 13, tzinfo=UTC)  # from the news list
    # Never opened: the other site, the category page, careers, anchors.
    assert not any("evil.example" in u or "category" in u or "careers" in u for u in seen)


def test_keywords_and_max_items():
    meta = Source("Meta newsroom", "ai", "rss", "https://openai.com/news/rss.xml", keywords=("Codex",))
    result, _ = fetch("ai", [meta], {meta.url: sample("openai_rss.xml")})
    assert [a.title for a in result.articles] == ["Codex for teams"]
    capped = Source("OpenAI", "ai", "rss", OPENAI.url, max_items=1)
    result, _ = fetch("ai", [capped], {OPENAI.url: sample("openai_rss.xml")})
    assert [a.title for a in result.articles] == ["Introducing GPT-7"]


def test_duplicates_across_sources_are_dropped():
    mirror = Source("Mirror", "ai", "rss", "https://openai.com/mirror.xml")
    result, _ = fetch("ai", [OPENAI, mirror], {OPENAI.url: sample("openai_rss.xml"), mirror.url: sample("openai_rss.xml")})
    assert [a.title for a in result.articles] == ["Introducing GPT-7", "Codex for teams"]


# ---- redirects and failures -------------------------------------------------------------------


def test_redirects_only_within_the_same_site():
    google = Source("Google AI blog", "ai", "rss", "https://blog.google/technology/ai/rss/")
    moved = "https://blog.google/innovation-and-ai/technology/ai/rss/"
    result, _ = fetch("ai", [google], {google.url: (301, {"location": moved}), moved: sample("openai_rss.xml").replace(b"openai.com", b"blog.google")})
    assert result.failed == [] and len(result.articles) == 2

    result, seen = fetch("ai", [OPENAI], {OPENAI.url: (302, {"location": "https://evil.example/feed.xml"})})
    assert result.failed == [{"source": "OpenAI", "reason": "refused a redirect to another site (evil.example)"}]
    assert "https://evil.example/feed.xml" not in seen


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (b"<rss><channel><item><title>broken", "the feed isn't valid RSS or Atom"),
        ((404, {}), "the site answered 404"),
        ((500, {}), "the site answered 500"),
        (b"x" * (MAX_BYTES + 10), "it's too big (over 4 MB)"),
        (httpx.ReadTimeout("slow"), "it timed out"),
        (httpx.ConnectError("down"), "couldn't connect"),
    ],
    ids=["broken-xml", "404", "500", "too-big", "timeout", "no-connection"],
)
def test_a_failing_source_is_listed_and_the_others_still_work(answer, reason):
    result, _ = fetch("ai", [OPENAI, DEEPMIND], {OPENAI.url: answer, DEEPMIND.url: sample("deepmind_atom.xml")})
    assert result.failed == [{"source": "OpenAI", "reason": reason}]
    assert result.read == ["Google DeepMind"] and len(result.articles) == 1


def test_only_the_topics_sources_are_read():
    _, seen = fetch("pakistan", [OPENAI, GEO], {GEO.url: sample("geo_rss.xml")})
    assert seen == [GEO.url]


# ---- helpers ---------------------------------------------------------------------------------


def test_dates_and_urls():
    assert parse_date("Thu, 15 Oct 2026 09:11:00 +05:00") == datetime(2026, 10, 15, 4, 11, tzinfo=UTC)
    assert parse_date("2026-10-15T17:20:00.000Z") == datetime(2026, 10, 15, 17, 20, tzinfo=UTC)
    assert parse_date("Released 2026/09/10") == datetime(2026, 9, 10, tzinfo=UTC)
    assert parse_date("October 6, 2026") == datetime(2026, 10, 6, tzinfo=UTC)
    assert parse_date("soon") is None and parse_date("") is None
    assert normalize_url("https://www.Dawn.com/news/1/?utm_source=x&id=2#top") == "https://dawn.com/news/1?id=2"


def test_articles_are_stored_once_and_old_ones_pruned():
    from datetime import timedelta

    from sqlalchemy import select

    from junior.db import NewsArticle, session_scope
    from junior.db.models import utcnow
    from junior.news.reader import Article
    from junior.news.store import save_articles

    fresh = Article("OpenAI", "ai", "Introducing GPT-7", "https://openai.com/index/gpt-7/", utcnow(), "New model.")
    old = Article("OpenAI", "ai", "Old", "https://openai.com/index/old/", utcnow() - timedelta(days=40))
    ids = save_articles([fresh, old])
    again = save_articles([Article("OpenAI", "ai", "Introducing GPT-7 (updated)", fresh.url, utcnow())])
    assert again[fresh.url] == ids[fresh.url]  # same row, refreshed
    with session_scope() as s:
        titles = list(s.scalars(select(NewsArticle.title)))
    assert titles == ["Introducing GPT-7 (updated)"]  # the 40-day-old one was pruned
