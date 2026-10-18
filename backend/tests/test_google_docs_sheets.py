"""Google Docs and Sheets: create (through the gate, only when you ask), read (fenced as outside text)."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from junior.agent.context import TurnContext
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.google import auth
from junior.google.docs import doc_id, layout
from junior.google.fake import SCOPES, FakeGoogle
from junior.google.sheets import sheet_id
from junior.google.tools import doc_create_for, doc_read_for, sheet_create_for, sheet_read_for
from junior.main import create_app
from junior.permissions import set_rule
from junior.registry import load_registry
from junior.settings_store import all_settings


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
                chat = Conversation(title="Google")
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


def test_links_give_their_ids():
    assert doc_id("https://docs.google.com/document/d/1AbCdEfGhIjK_lm-NoP/edit?tab=t.0") == "1AbCdEfGhIjK_lm-NoP"
    assert sheet_id("https://docs.google.com/spreadsheets/d/1ZyXwVuTsRq_po-NmL/edit#gid=0") == "1ZyXwVuTsRq_po-NmL"
    with pytest.raises(auth.GoogleError, match="Google Doc link"):
        doc_id("https://example.com/not-a-doc")


def test_markdown_becomes_headings_bullets_and_bold():
    text, styles = layout("# Plan\n- one **two**\n1. first")
    assert text == "Plan\none two\nfirst\n"
    assert {"updateParagraphStyle": {"range": {"startIndex": 1, "endIndex": 6}, "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                     "fields": "namedStyleType"}} in styles
    assert styles[1]["createParagraphBullets"]["range"] == {"startIndex": 6, "endIndex": 14}
    assert styles[2]["updateTextStyle"]["range"] == {"startIndex": 10, "endIndex": 13}  # "two"
    assert styles[3]["createParagraphBullets"]["bulletPreset"] == "NUMBERED_DECIMAL_ALPHA_ROMAN"


def test_you_ask_for_a_doc_and_get_its_link(google):
    said, fake = google
    context = said("make a google doc of my research plan")
    answer = run(doc_create_for(context, "Research plan", "# Goal\nAn AI tutor.", "make a google doc of my research plan"))
    assert "https://docs.google.com/document/d/doc-1/edit" in answer
    assert fake.docs["doc-1"]["title"] == "Research plan" and "An AI tutor." in fake.docs["doc-1"]["text"]
    assert context.actions_done == 1


def test_no_doc_without_your_words_or_against_your_rule(google):
    said, fake = google
    context = said("tell me about AI tutors")
    assert run(doc_create_for(context, "X", "y", "make a google doc")).startswith("NOT done")
    set_rule("google.docs.create", "deny")
    context = said("make a google doc of it")
    assert run(doc_create_for(context, "X", "y", "make a google doc of it")).startswith("NOT done")
    assert len(fake.docs) == 1  # only the one that was there


def test_reading_a_doc_is_fenced_outside_text(google):
    said, _ = google
    context = said("summarize this doc")
    text = run(doc_read_for(context, "https://docs.google.com/document/d/doc-plan/edit"))
    assert "START OF THEIR TEXT (the Google Doc 'Research plan'" in text and "AI tutor for Urdu speakers" in text
    assert context.outside_content_seen  # no memory saving from it this turn
    assert run(doc_read_for(context, "https://docs.google.com/document/d/doc-missing123/edit")).startswith("Couldn't read it")


def test_a_sheet_from_a_list_written_as_plain_text(google):
    said, fake = google
    context = said("find the professors and put them in a google sheet")
    rows = [["Dr. A", "CS", "a@uni.edu", "https://uni.edu/a"], ["Dr. B", "AI", "=IMPORTXML(\"x\")"]]
    answer = run(sheet_create_for(context, "Professors", ["Name", "Dept", "Email", "Source"], rows, "put them in a google sheet"))
    assert "with 2 rows: https://docs.google.com/spreadsheets/d/sheet-1/edit" in answer
    sheet = fake.sheets["sheet-1"]
    assert sheet["tabs"]["Sheet1"][0] == ["Name", "Dept", "Email", "Source"]
    assert sheet["tabs"]["Sheet1"][2] == ["Dr. B", "AI", "=IMPORTXML(\"x\")", ""]  # padded; kept as text
    assert sheet["value_input"] == "RAW"  # never run as a formula
    assert any("repeatCell" in r for r in sheet["formatting"])  # bold header


def test_reading_a_sheet(google):
    said, _ = google
    context = said("how much did I earn")
    text = run(sheet_read_for(context, "https://docs.google.com/spreadsheets/d/sheet-income/edit"))
    assert text.startswith("Tabs: Sheet1. Read: 'Sheet1', 3 rows")
    assert "3: Oct | 1200" in text and "START OF THEIR TEXT" in text
    assert context.outside_content_seen


def test_not_connected_or_not_allowed_says_how_to_fix(google, monkeypatch):
    said, _ = google
    context = said("make a google doc of it")
    auth._save("you@example.com", "fake-refresh", "openid email https://www.googleapis.com/auth/drive.file")
    assert "didn't allow reading your Google Docs" in run(doc_read_for(context, "doc-plan-xyz123"))
    auth.forget()
    assert "Connect Google" in run(doc_create_for(context, "X", "y", "make a google doc of it"))


def test_junior_muneer_has_the_google_tools():
    assert "google" in load_registry().get("junior_muneer").tools
