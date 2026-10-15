"""P2b-05: the morning digests (scheduler) and the News API."""

import asyncio
import json
from datetime import UTC, datetime, time, timedelta
from email.utils import format_datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_ai import ScriptedModel, assistant_message
from junior.agent.builder import NoApiKeyError
from junior.db import NewsDigest, session_scope
from junior.main import create_app
from junior.news import digest as digest_module
from junior.news.digest import morning_digests
from junior.news.reader import fetch_topic as real_fetch_topic
from junior.news.sources import Source
from junior.pause import set_paused
from junior.registry import load_registry
from junior.settings_store import set_setting

PKT = ZoneInfo("Asia/Karachi")
OPENAI = Source("OpenAI", "ai", "rss", "https://openai.com/news/rss.xml")
DAWN = Source("Dawn", "pakistan", "rss", "https://www.dawn.com/feeds/pakistan")


def rss(title, link) -> bytes:
    when = format_datetime(datetime.now(UTC) - timedelta(hours=2))
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><item><title>{title}</title><link>{link}</link>'
        f"<pubDate>{when}</pubDate></item></channel></rss>"
    ).encode()


FEEDS = {
    OPENAI.url: rss("Introducing GPT-7", "https://openai.com/index/gpt-7/"),
    DAWN.url: rss("Petrol price cut", "https://www.dawn.com/news/1/petrol"),
}


@pytest.fixture(autouse=True)
def offline_news(monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=FEEDS[str(r.url)]) if str(r.url) in FEEDS else httpx.Response(404))
    monkeypatch.setattr(digest_module, "load_sources", lambda: [OPENAI, DAWN])
    monkeypatch.setattr(
        digest_module, "fetch_topic", lambda topic, sources, now=None, transport=None: real_fetch_topic(topic, sources, now=now, transport=transport_)
    )
    transport_ = transport
    digest_module._last_try.clear()


def answer(key, headline):
    return [assistant_message(json.dumps({"sections": [{"key": key, "items": [{"article_ids": [1 if key == "models" else 2], "headline": headline, "summary": ""}]}]}))]


def today_at(hour, minute=0) -> datetime:
    local_today = datetime.now(UTC).astimezone(PKT).date()
    return datetime.combine(local_today, time(hour, minute), tzinfo=PKT)


def digests() -> list[str]:
    with session_scope() as s:
        return list(s.scalars(select(NewsDigest.topic).order_by(NewsDigest.id)))


# ---- the morning job --------------------------------------------------------------------------


def test_both_digests_are_built_once_after_the_morning_time():
    model = ScriptedModel([answer("models", "GPT-7"), answer("economy", "Petrol cheaper")])
    run = lambda now: asyncio.run(morning_digests(load_registry(), lambda: (lambda _n: model), now))  # noqa: E731

    assert run(today_at(6, 0)) == []  # before 07:30 local time
    assert run(today_at(8, 0)) == ["ai", "pakistan"]
    assert digests() == ["ai", "pakistan"]
    assert run(today_at(9, 0)) == []  # already built today

    set_setting("news_digest_time", "06:15")
    assert run(today_at(6, 20)) == []  # the time changed, but today's digests exist


@pytest.mark.parametrize("why", ["off", "paused", "no key", "budget"])
def test_the_morning_job_is_skipped(why):
    model = ScriptedModel()
    factory = lambda: (lambda _n: model)  # noqa: E731
    if why == "off":
        set_setting("news_digest_enabled", False)
    elif why == "paused":
        set_paused(True)
    elif why == "no key":
        def factory():
            raise NoApiKeyError("No OpenAI API key yet.")
    elif why == "budget":
        set_setting("daily_cap_usd", 0.0)
    assert asyncio.run(morning_digests(load_registry(), factory, today_at(8))) == []
    assert digests() == [] and model.calls == ()


def test_a_failed_build_is_retried_after_30_minutes():
    def broken():
        raise RuntimeError("network down")

    calls = []

    def factory():
        calls.append(1)
        return broken()

    asyncio.run(morning_digests(load_registry(), factory, today_at(8, 0)))
    asyncio.run(morning_digests(load_registry(), factory, today_at(8, 10)))  # too soon: skipped
    assert len(calls) == 2  # one try per topic
    asyncio.run(morning_digests(load_registry(), factory, today_at(8, 31)))
    assert len(calls) == 4


def test_the_scheduler_runs_async_jobs_too():
    from junior.scheduler import run_due_jobs

    ran = []

    async def job():
        ran.append("async")

    asyncio.run(run_due_jobs([("test job", job)]))
    assert ran == ["async"]


# ---- the API ----------------------------------------------------------------------------------


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    with TestClient(create_app(model_provider=lambda: (lambda _name: model))) as c:
        yield c


def test_news_api_refresh_and_read(client, model):
    assert client.get("/api/news/ai").json() == {"topic": "ai", "digest": None}
    model.enqueue(answer("models", "OpenAI releases GPT-7"))
    built = client.post("/api/news/ai/refresh").json()["digest"]
    assert built["sections"][0]["items"][0]["sources"][0]["url"] == "https://openai.com/index/gpt-7/"
    assert built["label"] == "AI" and built["articles"] == 1 and built["failed"] == []
    got = client.get("/api/news/ai").json()["digest"]
    assert got["id"] == built["id"] and got["built_at"]
    assert client.get("/api/news/sports").status_code == 404
    assert "news" in {a["kind"] for a in client.get("/api/activity").json()}


def test_refresh_when_the_budget_is_used_up(client):
    set_setting("daily_cap_usd", 0.0)
    r = client.post("/api/news/pakistan/refresh")
    assert r.status_code == 409 and "cap" in r.json()["detail"].lower()


def test_sources_list(client):
    data = client.get("/api/news-sources").json()
    assert {s["name"] for s in data["ai"]} >= {"OpenAI", "Anthropic"}
    assert {s["name"] for s in data["pakistan"]} >= {"Dawn", "Google Trends Pakistan"}
    assert data["rankings"] is False


def test_news_settings(client):
    assert client.patch("/api/settings", json={"news_digest_time": "06:45", "news_digest_enabled": False}).status_code == 200
    s = client.get("/api/settings").json()
    assert s["news_digest_time"] == "06:45" and s["news_digest_enabled"] is False
    assert client.patch("/api/settings", json={"news_digest_time": "25:00"}).status_code == 422
