"""Changing settings by asking in chat: everyday settings only, from your own words, never from outside text."""

import pytest
from fastapi.testclient import TestClient

from junior.agent.context import TurnContext
from junior.agent.tools import TOOL_FACTORIES
from junior.db import Conversation, Message, session_scope
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_chat import CHANGEABLE, PAGE_ONLY, change_setting_for, current_settings
from junior.settings_store import all_settings, get_setting


@pytest.fixture
def said():
    """A turn where the user said something: returns a function making its context."""
    with TestClient(create_app()):

        def make(words: str, **extra) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Settings")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids, **extra)

        yield make


def test_switching_the_model_when_you_ask(said):
    context = said("switch to deepseek pro please")
    answer = change_setting_for(context, "main_model", "deepseek:deepseek-v4-pro", "switch to deepseek pro")
    assert answer.startswith("Changed main_model")
    assert get_setting("main_model") == "deepseek:deepseek-v4-pro"
    assert context.settings["main_model"] == "deepseek:deepseek-v4-pro"
    # Back to the default
    assert change_setting_for(context, "main_model", "default", "switch to deepseek pro").startswith("Changed")
    assert get_setting("main_model") == ""


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("language", "Urdu", "urdu"),
        ("whatsapp_session_hours", "6 hours", 6),
        ("whatsapp_session_hours", "every message", 0),
        ("briefing_enabled", "off", False),
        ("whatsapp_carry_summary", "no", False),
        ("tts_speed", "1.2", 1.2),
        ("briefing_time", "07:00", "07:00"),
    ],
)
def test_everyday_settings_change(said, setting, value, expected):
    context = said("please change this setting for me")
    assert change_setting_for(context, setting, value, "change this setting").startswith("Changed")
    assert get_setting(setting) == expected


def test_bad_values_are_refused_with_the_reason(said):
    context = said("use the gpt-99 model")
    answer = change_setting_for(context, "main_model", "gpt-99", "use the gpt-99 model")
    assert answer.startswith("NOT changed") and "deepseek:deepseek-flash" in answer  # lists the real models
    assert change_setting_for(context, "whatsapp_session_hours", "5", "use the gpt-99 model").startswith("NOT changed")
    assert change_setting_for(context, "briefing_time", "25:00", "use the gpt-99 model").startswith("NOT changed")
    assert change_setting_for(context, "briefing_enabled", "maybe", "use the gpt-99 model").startswith("NOT changed")
    assert get_setting("main_model") == ""


@pytest.mark.parametrize("setting", sorted(PAGE_ONLY))
def test_money_and_safety_settings_stay_on_the_settings_page(said, setting):
    before = all_settings()
    context = said("raise my daily limit to 100 and unpause")
    answer = change_setting_for(context, setting, "100", "raise my daily limit to 100")
    assert answer.startswith("NOT changed") and "Settings page" in answer
    assert all_settings() == before


def test_your_own_words_are_needed(said):
    context = said("hi, how are you?")
    assert change_setting_for(context, "language", "urdu", "reply in urdu").startswith("NOT changed")
    assert change_setting_for(context, "language", "urdu", "hi").startswith("NOT changed")  # too short
    assert get_setting("language") == "match"


def test_outside_text_blocks_changes(said):
    # A paste, a web result or a feed in the turn: someone else's words could be asking.
    context = said("switch to deepseek pro please")
    context.mark_outside()
    assert change_setting_for(context, "main_model", "deepseek:deepseek-v4-pro", "switch to deepseek pro").startswith(
        "NOT changed"
    )
    pasted = said("switch to deepseek pro please", paste={"platform": "upwork", "kind": "job"})
    assert change_setting_for(pasted, "main_model", "deepseek:deepseek-v4-pro", "switch to deepseek pro").startswith(
        "NOT changed"
    )
    background = said("switch to deepseek pro please", background=True)
    assert change_setting_for(
        background, "main_model", "deepseek:deepseek-v4-pro", "switch to deepseek pro"
    ).startswith("NOT changed")
    assert get_setting("main_model") == ""


def test_changes_are_in_the_activity_log(said):
    context = said("turn off the morning briefing")
    change_setting_for(context, "briefing_enabled", "off", "turn off the morning briefing")
    with TestClient(create_app()) as c:
        rows = c.get("/api/activity").json()
        items = rows["items"] if isinstance(rows, dict) else rows
        entry = next(r for r in items if r["kind"] == "setting" and r["name"] == "briefing_enabled")
        assert entry["detail"] == {"before": True, "after": False, "by": "chat"}


def test_junior_muneer_has_the_tools_and_sees_current_values(said):
    assert "settings" in load_registry().get("junior_muneer").tools
    assert [t.name for t in TOOL_FACTORIES["settings"]()] == ["my_settings", "change_setting"]
    listing = current_settings()
    assert "main_model = the default" in listing and "daily spending limit" in listing
    assert not set(CHANGEABLE) & set(PAGE_ONLY)
