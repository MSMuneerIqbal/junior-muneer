"""Email yourself anything you ask for (news, drafts, notes): only to your own Gmail, only when you ask."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from junior import mailer
from junior.agent.context import TurnContext
from junior.agent.tools import TOOL_FACTORIES, email_me_for
from junior.gate import MAX_ACTIONS_PER_TURN
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.main import create_app
from junior.mailer import markdown_html
from junior.permissions import set_rule
from junior.registry import load_registry
from junior.settings_store import all_settings, set_setting


@pytest.fixture
def mail(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(mailer, "SENDER", sent.append)
    with TestClient(create_app()):

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Email")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids)

        yield said, sent
    get_settings.cache_clear()


def run(context, subject="AI news", body="**Top story**\n- GPT-7 is out: https://openai.com/gpt-7", words="email me the AI news"):
    return asyncio.run(email_me_for(context, subject, body, words))


def test_it_emails_you_what_you_asked_for(mail):
    said, sent = mail
    answer = run(said("please email me the AI news"))
    assert answer.startswith("Sent to me@example.com")
    [email] = sent
    assert email["To"] == "me@example.com" and email["Subject"] == "AI news"
    assert "GPT-7 is out" in email.get_body(("plain",)).get_content()
    html = email.get_body(("html",)).get_content()
    assert "<b>Top story</b>" in html and 'href="https://openai.com/gpt-7"' in html


def test_news_with_outside_text_in_the_turn_can_still_be_emailed_to_you(mail):
    # News is outside text, but the email only ever goes to you, and you asked for it.
    said, sent = mail
    context = said("email me the AI news")
    context.mark_outside()
    assert run(context).startswith("Sent")
    assert len(sent) == 1


def test_only_when_you_ask(mail):
    said, sent = mail
    context = said("what's new in AI?")
    assert run(context).startswith("NOT")  # these words aren't yours
    assert run(context, words="new").startswith("NOT")  # too short to be a quote
    assert sent == []


@pytest.mark.parametrize("rule", ["ask", "deny"])
def test_your_rule_can_stop_it(mail, rule):
    said, sent = mail
    set_rule("gmail.to_self", rule)
    assert run(said("email me the AI news")).startswith("NOT")
    assert sent == []


def test_paused_means_not_sent(mail):
    said, sent = mail
    set_setting("paused", True)
    assert "paused" in run(said("email me the AI news"))
    assert sent == []


def test_a_few_actions_per_message_at_most(mail):
    said, sent = mail
    context = said("email me the AI news")
    for _ in range(MAX_ACTIONS_PER_TURN):
        assert run(context).startswith("Sent")
    assert run(context).startswith("NOT")
    assert len(sent) == MAX_ACTIONS_PER_TURN


def test_without_gmail_it_says_what_to_add(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()):
            context = TurnContext(conversation_id=None, settings=all_settings())
            assert "GMAIL_APP_PASSWORD" in run(context)
    finally:
        get_settings.cache_clear()


def test_there_is_no_way_to_email_someone_else():
    import inspect

    assert list(inspect.signature(email_me_for).parameters) == ["context", "subject", "body", "your_words"]
    assert list(inspect.signature(mailer.send_to_self).parameters) == ["subject", "text", "body_html"]


def test_junior_muneer_has_the_tool():
    assert "email" in load_registry().get("junior_muneer").tools
    assert [t.name for t in TOOL_FACTORIES["email"]()] == ["email_me"]


def test_markdown_becomes_simple_html():
    html = markdown_html("## Plan\n- one **two**\n\nSee [the post](https://x.com/a) or https://openai.com/b.")
    assert "Plan</div>" in html and "• one <b>two</b>" in html
    assert '<a href="https://x.com/a" style="color:#c96442">the post</a>' in html
    assert '<a href="https://openai.com/b" style="color:#c96442">https://openai.com/b</a>.' in html
    assert "&lt;script&gt;" in markdown_html("<script>alert(1)</script>")
