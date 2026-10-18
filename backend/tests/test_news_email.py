"""The day's top 5 news, and the top 5 AI news emailed to your own Gmail."""

import asyncio
import smtplib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from junior.config import get_settings
from junior.db import NewsDigest, session_scope
from junior.main import create_app
from junior import mailer
from junior.news import mail
from junior.news.guard import top_stories
from junior.permissions import set_rule
from junior.settings_store import get_setting, set_setting
from junior.timeutil import zone

NOW = datetime.now(UTC)


def item(headline, importance=None, days_ago=0):
    entry = {
        "headline": headline,
        "summary": f"About {headline}.",
        "date": (NOW - timedelta(days=days_ago)).isoformat(),
        "sources": [{"name": "OpenAI", "title": headline, "url": f"https://openai.com/{headline}", "date": NOW.isoformat()}],
    }
    if importance is not None:
        entry["importance"] = importance
    return entry


def test_the_top_5_are_the_most_important_across_sections():
    sections = [
        {"key": "models", "title": "New models", "items": [item("a", 9), item("b", 3), item("c", 7)]},
        {"key": "agents", "title": "Agents", "items": [item("d", 10), item("e", 7, days_ago=2), item("f", 1)]},
    ]
    top = top_stories(sections)
    assert [i["headline"] for i in top] == ["d", "a", "c", "e", "b"]  # equal ratings: newest first
    assert top[0]["section"] == "Agents"


def test_older_digests_without_ratings_take_each_sections_top_item_in_turn():
    sections = [
        {"key": "models", "title": "New models", "items": [item("a"), item("b")]},
        {"key": "agents", "title": "Agents", "items": [item("c")]},
        {"key": "business", "title": "Business", "items": [item("d"), item("e"), item("f")]},
    ]
    assert [i["headline"] for i in top_stories(sections)] == ["a", "c", "d", "b", "e"]


@pytest.fixture
def gmail(monkeypatch):
    """A set-up Gmail whose emails are kept here instead of sent."""
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(mailer, "SENDER", sent.append)
    mail._last_try.clear()
    with TestClient(create_app()) as client:
        yield client, sent
    get_settings.cache_clear()


def add_digest(built_at=None):
    sections = [{"key": "models", "title": "New models and releases", "items": [item(f"story{n}", 10 - n) for n in range(7)]}]
    with session_scope() as s:
        s.add(NewsDigest(topic="ai", data={"topic": "ai", "label": "AI", "window_days": 15, "sections": sections}, cost_usd=0, built_at=built_at or NOW))


def test_the_email_has_the_top_5_with_links_and_goes_only_to_you(gmail):
    client, sent = gmail
    add_digest()
    result = client.post("/api/news-email/send")
    assert result.status_code == 200, result.text
    assert result.json()["message"] == "Sent the top 5 AI news to me@example.com."
    [email] = sent
    assert email["To"] == "me@example.com" and "me@example.com" in email["From"]
    assert email["Subject"].startswith("Your top 5 AI news")
    text = email.get_body(("plain",)).get_content()
    assert "1. story0" in text and "5. story4" in text and "story5" not in text
    assert "https://openai.com/story0" in email.get_body(("html",)).get_content()
    assert get_setting("news_emailed_on") == datetime.now(UTC).astimezone(zone("Asia/Karachi")).date().isoformat()
    status = client.get("/api/news-email").json()
    assert status["configured"] and status["address"] == "me@example.com" and status["rule"] == "auto"


def test_each_morning_it_waits_for_todays_digest_then_sends_once(gmail):
    _, sent = gmail
    add_digest(built_at=NOW - timedelta(days=1))  # yesterday's
    assert not asyncio.run(mail.daily_news_email())
    add_digest()
    assert asyncio.run(mail.daily_news_email())
    mail._last_try.clear()
    assert not asyncio.run(mail.daily_news_email())  # already sent today
    assert len(sent) == 1


@pytest.mark.parametrize("why", ["switched off", "paused", "rule ask", "rule deny"])
def test_no_email_by_itself_when_you_said_no(gmail, why):
    _, sent = gmail
    add_digest()
    if why == "switched off":
        set_setting("news_email_enabled", False)
    elif why == "paused":
        set_setting("paused", True)
    else:
        set_rule("gmail.news_to_self", why.split()[1])
    assert not asyncio.run(mail.daily_news_email())
    assert sent == []


def test_deny_stops_even_send_now(gmail):
    client, sent = gmail
    add_digest()
    set_rule("gmail.news_to_self", "deny")
    r = client.post("/api/news-email/send")
    assert r.status_code == 400 and "Deny" in r.json()["detail"]
    set_rule("gmail.news_to_self", "ask")  # your click is the OK for Ask
    assert client.post("/api/news-email/send").status_code == 200
    assert len(sent) == 1


def test_a_wrong_app_password_says_so_plainly(gmail, monkeypatch):
    client, _ = gmail
    add_digest()

    def refuse(_message):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(mailer, "SENDER", refuse)
    r = client.post("/api/news-email/send")
    assert r.status_code == 400 and "App Password" in r.json()["detail"]
    assert get_setting("news_emailed_on") == ""


def test_without_gmail_it_explains_what_to_add(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            add_digest()
            assert client.get("/api/news-email").json()["configured"] is False
            r = client.post("/api/news-email/send")
            assert r.status_code == 400 and "GMAIL_APP_PASSWORD" in r.json()["detail"]
            assert not asyncio.run(mail.daily_news_email())
    finally:
        get_settings.cache_clear()


def test_the_api_digest_has_its_top_5(gmail):
    client, _ = gmail
    add_digest()
    top = client.get("/api/news/ai").json()["digest"]["top"]
    assert [i["headline"] for i in top] == [f"story{n}" for n in range(5)]
