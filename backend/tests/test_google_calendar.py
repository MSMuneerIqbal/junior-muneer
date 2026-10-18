"""Google Calendar: add events when you ask (your own calendar, nobody invited), see what's coming, and today's
events in the morning briefing."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from junior.agent.context import TurnContext
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.google import auth
from junior.google.calendar import describe, today_for_briefing
from junior.google.fake import SCOPES, FakeGoogle
from junior.google.tools import calendar_add_for, calendar_list_for
from junior.main import create_app
from junior.permissions import set_rule
from junior.reports import briefing_prompt
from junior.settings_store import all_settings
from junior.timeutil import zone

TZ = "Asia/Karachi"


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    get_settings.cache_clear()
    fake = FakeGoogle()
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(fake))
    auth._access.clear()
    with TestClient(create_app()):
        auth._save("you@example.com", "fake-refresh", SCOPES)

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Calendar")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids)

        yield said, fake
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def soon(days: int, hour: int = 10) -> str:
    local = datetime.now(UTC).astimezone(zone(TZ)) + timedelta(days=days)
    return local.strftime(f"%Y-%m-%d {hour:02d}:00")


def test_adding_an_event_you_asked_for(google):
    said, fake = google
    context = said("add my data mining exam on friday at 10am to my calendar")
    answer = run(calendar_add_for(context, "Data Mining exam", soon(3), "add my data mining exam", location="Room 4",
                                  reminder_minutes=60))
    assert answer.startswith("Added to their Google Calendar:") and "Data Mining exam (at Room 4)" in answer
    [event] = fake.events
    assert event["start"]["timeZone"] == TZ and event["start"]["dateTime"].endswith("+05:00")
    assert event["end"]["dateTime"][11:16] == "11:00"  # one hour by default
    assert event["reminders"]["overrides"] == [{"method": "popup", "minutes": 60}]
    assert "attendees" not in event  # nobody is ever invited


def test_all_day_events_end_the_next_day_for_google(google):
    said, fake = google
    context = said("put my trip to Hunza on the calendar")
    run(calendar_add_for(context, "Hunza trip", soon(5)[:10], "put my trip to Hunza", end=soon(7)[:10], all_day=True))
    event = fake.events[0]
    assert event["start"] == {"date": soon(5)[:10]} and event["end"] == {"date": soon(8)[:10]}
    assert describe(event, TZ).endswith("Hunza trip")
    assert " to " in describe(event, TZ) and "all day" in describe(event, TZ)


def test_unclear_or_backwards_times_are_refused(google):
    said, fake = google
    context = said("add the meeting to my calendar")
    assert "couldn't read the time" in run(calendar_add_for(context, "Meeting", "next friday", "add the meeting"))
    assert "ends before it starts" in run(calendar_add_for(context, "Meeting", soon(2, 15), "add the meeting", end=soon(2, 14)))
    assert fake.events == []


def test_only_when_you_ask_and_your_rule_allows(google):
    said, fake = google
    context = said("what's on this week?")
    assert run(calendar_add_for(context, "X", soon(1), "add my exam")).startswith("NOT done")
    set_rule("google.calendar.create", "ask")
    context = said("add my exam tomorrow")
    assert run(calendar_add_for(context, "Exam", soon(1), "add my exam tomorrow")).startswith("NOT done by itself")
    assert fake.events == []


def test_whats_coming_is_fenced_and_searchable(google):
    said, _ = google
    adder = said("add my exam and the meeting")
    run(calendar_add_for(adder, "Exam", soon(2), "add my exam"))
    run(calendar_add_for(adder, "Team meeting", soon(1, 15), "add my exam"))
    run(calendar_add_for(adder, "Far away", soon(20), "add my exam"))
    context = said("what's on this week?")
    text = run(calendar_list_for(context, 7))
    assert text.index("Team meeting") < text.index("Exam") and "Far away" not in text
    assert "START OF THEIR TEXT" in text and context.outside_content_seen
    assert "Team meeting" not in run(calendar_list_for(said("when is my exam?"), 30, "exam"))
    assert run(calendar_list_for(said("anything tomorrow?"), 1, "dentist")).startswith("Nothing on their Google Calendar")


def test_todays_events_go_into_the_morning_briefing(google):
    said, _ = google
    later_today = (datetime.now(UTC).astimezone(zone(TZ)) + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
    if later_today[:10] != soon(0)[:10]:
        pytest.skip("too close to midnight")
    run(calendar_add_for(said("add the call today"), "Call with Ali", later_today, "add the call today"))
    calendar = run(today_for_briefing(TZ))
    assert "Call with Ali" in calendar
    prompt = briefing_prompt(all_settings(), calendar=calendar)
    assert "### Today on their Google Calendar\n- " in prompt


def test_the_briefing_goes_on_without_google(google):
    auth.forget()
    assert run(today_for_briefing(TZ)) == ""
    assert "Google Calendar" not in briefing_prompt(all_settings())
