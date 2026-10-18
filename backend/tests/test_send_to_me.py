"""Send yourself anything you ask for, on Gmail or WhatsApp (a Google Doc as a Word file too): only to your own
address or number, only when you ask, through the gate."""

import asyncio
import inspect
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import mailer, whatsapp
from junior.agent.context import TurnContext
from junior.agent.tools import TOOL_FACTORIES, send_to_me_for
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.gate import MAX_ACTIONS_PER_TURN
from junior.google import auth
from junior.google.fake import SCOPES, FakeGoogle
from junior.main import create_app
from junior.mailer import markdown_html
from junior.permissions import set_rule
from junior.registry import load_registry
from junior.settings_store import all_settings, set_setting

BODY = "**Top story**\n- GPT-7 is out: https://openai.com/gpt-7"


@pytest.fixture
def me(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100200300")
    monkeypatch.setenv("WHATSAPP_OWNER_NUMBER", "923001112233")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    get_settings.cache_clear()
    emails, wa = [], {"sent": [], "uploads": [], "fail": ""}

    def whatsapp_api(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            wa["uploads"].append(request.content)
            return httpx.Response(200, json={"id": "media-1"})
        if wa["fail"]:
            return httpx.Response(400, json={"error": {"code": 131047, "message": wa["fail"]}})
        wa["sent"].append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    google = FakeGoogle()
    monkeypatch.setattr(mailer, "SENDER", emails.append)
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(whatsapp_api))
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(google))
    auth._access.clear()
    with TestClient(create_app()):

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Send")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids)

        yield said, emails, wa, google
    get_settings.cache_clear()


def send(context, where="gmail", words="email me the AI news", file_link="", subject="AI news", body=BODY, as_pdf=False):
    return asyncio.run(send_to_me_for(context, where, subject, body, words, file_link, as_pdf))


def test_gmail_gets_what_you_asked_for(me):
    said, emails, _, _ = me
    assert send(said("please email me the AI news")).startswith("Sent to me@example.com")
    [email] = emails
    assert email["To"] == "me@example.com" and email["Subject"] == "AI news"
    assert "GPT-7 is out" in email.get_body(("plain",)).get_content()
    html = email.get_body(("html",)).get_content()
    assert "<b>Top story</b>" in html and 'href="https://openai.com/gpt-7"' in html


def test_whatsapp_gets_it_on_your_own_number(me):
    said, _, wa, _ = me
    assert send(said("whatsapp me the AI news"), "whatsapp", "whatsapp me the AI news").startswith("Sent to their WhatsApp")
    [message] = wa["sent"]
    assert message["to"] == "923001112233" and message["type"] == "text"
    assert message["text"]["body"].startswith("*AI news*\n\n*Top story*")  # WhatsApp's own bold


def test_a_google_doc_goes_as_a_word_file(me):
    said, emails, wa, google = me
    auth._save("you@example.com", "fake-refresh", SCOPES)
    link = "https://docs.google.com/document/d/doc-plan/edit"
    answer = send(said("make my research plan a doc and send it on whatsapp and gmail"), "whatsapp", "send it on whatsapp", link)
    assert "with the file 'Research plan.docx'" in answer
    document = wa["sent"][1]
    assert document["type"] == "document" and document["document"] == {"id": "media-1", "filename": "Research plan.docx"}
    assert b"AI tutor for Urdu speakers" in wa["uploads"][0]
    send(said("send it on gmail too"), "gmail", "send it on gmail too", link)
    [attached] = list(emails[0].iter_attachments())
    assert attached.get_filename() == "Research plan.docx"
    assert attached.get_content_type() == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_without_google_the_link_goes_instead(me):
    said, emails, _, _ = me
    link = "https://docs.google.com/document/d/doc-plan/edit"
    answer = send(said("email me the doc please"), "gmail", "email me the doc", link)
    assert "link was sent instead" in answer
    assert link in emails[0].get_body(("plain",)).get_content()
    assert list(emails[0].iter_attachments()) == []


def test_whatsapps_24_hour_window_is_explained(me):
    said, _, wa, _ = me
    wa["fail"] = "Message failed to send because more than 24 hours have passed (re-engagement message)"
    answer = send(said("whatsapp me the AI news"), "whatsapp", "whatsapp me the AI news")
    assert answer.startswith("NOT sent: WhatsApp only lets the app message you within 24 hours") and "Gmail" in answer


def test_only_when_you_ask(me):
    said, emails, wa, _ = me
    context = said("what's new in AI?")
    assert send(context).startswith("NOT")  # these words aren't yours
    assert send(context, words="new").startswith("NOT")  # too short to be a quote
    assert send(context, "telegram").startswith("NOT sent: where must be")
    assert emails == [] and wa["sent"] == []


def test_news_in_the_turn_can_still_be_sent_to_you(me):
    # News is outside text, but it only ever goes to you, and you asked for it.
    said, emails, _, _ = me
    context = said("email me the AI news")
    context.mark_outside()
    assert send(context).startswith("Sent")
    assert len(emails) == 1


@pytest.mark.parametrize(("action", "where", "rule"), [("gmail.to_self", "gmail", "ask"), ("gmail.to_self", "gmail", "deny"),
                                                     ("whatsapp.to_self", "whatsapp", "deny")])
def test_your_rule_can_stop_it(me, action, where, rule):
    said, emails, wa, _ = me
    set_rule(action, rule)
    assert send(said("email me the AI news"), where).startswith("NOT")
    assert emails == [] and wa["sent"] == []


def test_paused_means_not_sent(me):
    said, emails, _, _ = me
    set_setting("paused", True)
    assert "paused" in send(said("email me the AI news"))
    assert emails == []


def test_a_few_per_message_at_most(me):
    said, emails, _, _ = me
    context = said("email me the AI news")
    for _ in range(MAX_ACTIONS_PER_TURN):
        assert send(context).startswith("Sent")
    assert send(context).startswith("NOT")
    assert len(emails) == MAX_ACTIONS_PER_TURN


def test_without_gmail_or_whatsapp_it_says_what_to_set_up(monkeypatch):
    for name in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "WHATSAPP_TOKEN"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()):
            context = TurnContext(conversation_id=None, settings=all_settings())
            assert "GMAIL_APP_PASSWORD" in send(context)
            assert "WhatsApp isn't connected" in send(context, "whatsapp")
    finally:
        get_settings.cache_clear()


def test_there_is_no_way_to_send_to_someone_else():
    assert list(inspect.signature(send_to_me_for).parameters) == [
        "context", "where", "subject", "message", "your_words", "file_link", "as_pdf"]
    assert list(inspect.signature(mailer.send_to_self).parameters) == ["subject", "text", "body_html", "attachments"]


def test_junior_muneer_has_the_tool():
    assert "email" in load_registry().get("junior_muneer").tools
    assert [t.name for t in TOOL_FACTORIES["email"]()] == ["send_to_me"]


def test_markdown_becomes_simple_html():
    html = markdown_html("## Plan\n- one **two**\n\nSee [the post](https://x.com/a) or https://openai.com/b.")
    assert "Plan</div>" in html and "• one <b>two</b>" in html
    assert '<a href="https://x.com/a" style="color:#c96442">the post</a>' in html
    assert '<a href="https://openai.com/b" style="color:#c96442">https://openai.com/b</a>.' in html
    assert "&lt;script&gt;" in markdown_html("<script>alert(1)</script>")
