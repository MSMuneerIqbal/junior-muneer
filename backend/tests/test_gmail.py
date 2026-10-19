"""Gmail (Phase 4): read and search, drafts that are sent only after you approve, the inbox watcher and WhatsApp
alerts for important emails."""

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.policy import default

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import inbox, whatsapp
from junior.agent.context import TurnContext
from junior.agent.fake import fake_model_provider
from junior.config import get_settings
from junior.db import Conversation, Email, Message, session_scope
from junior.google import auth
from junior.google.fake import SCOPES, FakeGoogle
from junior.google.gmail import summary_of
from junior.google.tools import gmail_draft_for, gmail_read_for, gmail_search_for
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_store import all_settings, get_setting, set_setting


@pytest.fixture
def gmail(monkeypatch):
    for name, value in {"GOOGLE_CLIENT_ID": "client-123", "GOOGLE_CLIENT_SECRET": "secret-xyz", "WHATSAPP_TOKEN": "token",
                        "WHATSAPP_PHONE_NUMBER_ID": "100200300", "WHATSAPP_OWNER_NUMBER": "923001112233",
                        "META_APP_SECRET": "s", "WHATSAPP_VERIFY_TOKEN": "v"}.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    google = FakeGoogle()
    wa = {"sent": [], "closed": False}

    def whatsapp_api(request: httpx.Request) -> httpx.Response:
        if wa["closed"]:
            return httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement message"}})
        wa["sent"].append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(google))
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(whatsapp_api))
    auth._access.clear()
    with TestClient(create_app(model_provider=fake_model_provider)) as client:
        auth._save("you@example.com", "fake-refresh", SCOPES)

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Mail")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids, convo = [msg.id], chat.id
            return TurnContext(conversation_id=convo, settings=all_settings(), user_message_ids=ids)

        yield client, said, google, wa
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def sent_email(google: FakeGoogle, n: int = 0):
    return message_from_bytes(base64.urlsafe_b64decode(google.sent[n]["raw"]), policy=default)


# ---- reading -------------------------------------------------------------------------------


def test_html_only_emails_become_readable_text():
    raw = base64.urlsafe_b64encode(b"<style>x{}</style><p>Hello <b>Muneer</b></p><p>Bye&nbsp;now</p>").decode()
    message = {"id": "abc123", "payload": {"headers": [{"name": "From", "value": "A <a@x.com>"}], "parts": [
        {"mimeType": "text/html", "body": {"data": raw}}]}}
    summary = summary_of(message)
    assert summary["body"] == "Hello Muneer\nBye now"
    assert summary["from_address"] == "a@x.com" and summary["subject"] == "(no subject)"


def test_searching_and_reading_are_fenced(gmail):
    _, said, _, _ = gmail
    context = said("any email from ali?")
    found = run(gmail_search_for(context, "from:ali"))
    assert "[msg0001client]" in found and "Quote for a chatbot" in found and "50% off" not in found
    assert "START OF THEIR TEXT" in found and context.outside_content_seen
    text = run(gmail_read_for(context, "msg0001client"))
    assert "From: Ali Khan <ali@acme.com>" in text and "a quote for a support chatbot by Friday" in text
    assert "Open in Gmail: https://mail.google.com/mail/u/0/#all/msg0001client" in text


# ---- writing: a draft, sent only when you approve -----------------------------------------


def test_a_new_email_waits_for_your_ok_then_goes_out_from_gmail(gmail):
    client, said, google, _ = gmail
    context = said("email sara@uni.edu that I'll send the report tomorrow")
    answer = run(gmail_draft_for(context, "sara@uni.edu", "Report", "Hi Sara,\n\nI'll send the report tomorrow.\n\nMuneer",
                                 "email sara@uni.edu that I'll send the report tomorrow"))
    assert "nothing is sent until they approve" in answer
    assert len(google.drafts) == 1 and google.sent == []  # in Gmail Drafts, not sent
    [card] = [e["item"] for e in context.pending_events if e["type"] == "approval"]
    assert card["status"] == "waiting" and card["action_type"] == "gmail.send" and card["title"] == "To sara@uni.edu: Report"

    edited = client.patch(f"/api/approvals/{card['id']}", json={"text": "Hi Sara,\n\nThe report comes tomorrow morning.\n\nMuneer"})
    assert edited.status_code == 200
    done = client.post(f"/api/approvals/{card['id']}/approve").json()
    assert done["status"] == "posted" and done["meta"]["post_url"].startswith("https://mail.google.com/")
    email = sent_email(google)
    assert email["To"] == "sara@uni.edu" and email["Subject"] == "Report"
    assert "The report comes tomorrow morning." in email.get_content()  # exactly what you approved
    assert google.drafts == {}  # the draft itself was sent


def test_a_reply_stays_in_the_thread_and_always_waits(gmail):
    client, said, google, _ = gmail
    context = said("reply to ali, say friday works")
    run(gmail_draft_for(context, "", "", "Hi Ali,\n\nFriday works. I'll send the quote then.\n\nMuneer",
                        "reply to ali, say friday works", reply_to="msg0001client"))
    card = context.pending_events[-1]["item"]
    assert card["action_type"] == "gmail.reply" and card["from_outside"] is True and card["can_always_allow"] is False
    assert card["title"] == "To ali@acme.com: Re: Quote for a chatbot"
    assert client.post(f"/api/approvals/{card['id']}/approve").json()["status"] == "posted"
    email = sent_email(google)
    assert email["In-Reply-To"] == "<ali-1@acme.com>" and google.sent[0]["threadId"] == "thr0001"


def test_a_reply_to_an_inbox_number(gmail):
    _, said, google, _ = gmail
    with session_scope() as s:
        s.add(Email(gmail_id="msg0001client", thread_id="thr0001", from_address="ali@acme.com", subject="Quote for a chatbot",
                    category="client", important=True, summary="Ali wants a quote"))
        s.flush()
        number = s.scalar(__import__("sqlalchemy").select(Email.id))
    context = said(f"junior reply to email {number}, say yes")
    assert "Drafted" in run(gmail_draft_for(context, "", "", "Yes!\n\nMuneer", f"reply to email {number}", reply_to=str(number)))
    assert run(gmail_read_for(context, str(number))).count("Quote for a chatbot") == 1


def test_with_the_rule_on_auto_a_new_email_goes_out_at_once(gmail):
    from junior.permissions import set_rule

    _, said, google, _ = gmail
    set_rule("gmail.send", "auto")
    context = said("send an email to sara@uni.edu that the meeting moved to 3pm")
    answer = run(gmail_draft_for(context, "sara@uni.edu", "Meeting at 3pm", "Hi Sara,\n\nThe meeting moved to 3pm.\n\nMuneer",
                                 "send an email to sara@uni.edu that the meeting moved to 3pm"))
    assert answer.startswith("Sent from their Gmail to sara@uni.edu")
    assert "The meeting moved to 3pm." in sent_email(google).get_content()
    card = context.pending_events[-1]["item"]
    assert card["status"] == "posted" and card["meta"]["approved_by"] == "auto rule"  # a record, nothing to approve


def test_auto_still_waits_for_replies_and_for_emails_after_reading_mail(gmail):
    from junior.permissions import set_rule

    _, said, google, _ = gmail
    set_rule("gmail.send", "auto")
    context = said("reply to ali, say friday works")
    run(gmail_draft_for(context, "", "", "Friday works.\n\nMuneer", "reply to ali, say friday works", reply_to="msg0001client"))
    assert context.pending_events[-1]["item"]["status"] == "waiting"  # replies answer someone else's text: always Ask
    context = said("read ali's email and email bob@x.com about it")
    run(gmail_read_for(context, "msg0001client"))  # someone else's text is now in this turn
    run(gmail_draft_for(context, "bob@x.com", "Ali's request", "Ali wants a quote.\n\nMuneer", "email bob@x.com about it"))
    assert context.pending_events[-1]["item"]["status"] == "waiting"
    assert google.sent == []


def test_bad_addresses_placeholders_and_your_words(gmail):
    client, said, google, _ = gmail
    context = said("email bob about the meeting")
    assert "isn't an email address" in run(gmail_draft_for(context, "bob", "Meeting", "Hi", "email bob about the meeting"))
    assert run(gmail_draft_for(said("what's new?"), "a@b.com", "x", "y", "email bob")).startswith("NOT done")
    context = said("email a@b.com hello")
    run(gmail_draft_for(context, "a@b.com", "Hello", "Hi [name], hello", "email a@b.com hello"))
    card = context.pending_events[-1]["item"]
    r = client.post(f"/api/approvals/{card['id']}/approve").json()
    assert r["status"] == "approved" and "placeholder" in " ".join(r["meta"]["blocked"])  # the Safety Guard stopped it
    assert google.sent == []


def test_approving_on_whatsapp_sends_it(gmail):
    _, said, google, _ = gmail
    context = said("email a@b.com that I'm running late")
    run(gmail_draft_for(context, "a@b.com", "Late", "Running 10 minutes late.\n\nMuneer", "email a@b.com that I'm running late"))
    card = context.pending_events[-1]["item"]

    class App:
        class state:
            from junior.senders.registry import CURRENT as senders

    assert run(whatsapp.on_button(f"approve:{card['id']}", App)) == "Sent: To a@b.com: Late."
    assert "Running 10 minutes late." in sent_email(google).get_content()


# ---- the watcher and WhatsApp alerts --------------------------------------------------------


def test_the_first_check_only_starts_the_clock(gmail):
    client, _, _, wa = gmail
    assert client.post("/api/emails/check").json() == {"new": 0}
    assert get_setting("email_watch_since") and wa["sent"] == []
    assert client.get("/api/emails").json()["items"] == []  # old mail isn't announced


def test_new_mail_is_sorted_and_important_ones_reach_whatsapp(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0003quote", **{"from": "Sara <sara@corp.com>", "subject": "Need a quote", "body": "Can you quote a RAG bot?"})
    google.add_mail(id="msg0004news", **{"from": "News <news@x.com>", "subject": "Weekly digest", "body": "Stories"})
    google.add_mail(id="msg0005promo", labels=["INBOX", "CATEGORY_PROMOTIONS"], **{"from": "Shop <s@x.com>", "subject": "Sale", "body": "quote"})
    assert client.post("/api/emails/check").json() == {"new": 3}
    items = {e["subject"]: e for e in client.get("/api/emails").json()["items"]}
    assert items["Need a quote"]["important"] and items["Need a quote"]["category"] == "client"
    assert not items["Weekly digest"]["important"]
    assert items["Sale"]["category"] == "promotion" and not items["Sale"]["important"]  # by Gmail's tab, no AI
    [alert] = wa["sent"]
    assert alert["to"] == "923001112233" and "Important email:" in alert["text"]["body"]
    assert "Sara" in alert["text"]["body"] and "Weekly digest" not in alert["text"]["body"]
    assert client.get("/api/emails?important=true").json()["items"][0]["notified"] is True
    assert client.post("/api/emails/check").json() == {"new": 0}  # nothing twice


def test_scams_are_flagged_as_important(gmail):
    client, _, google, _ = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0006scam", **{"from": "Bank <x@bank-secure.example>", "subject": "Urgent",
                                         "body": "Verify your account now: send your password here"})
    client.post("/api/emails/check")
    [scam] = client.get("/api/emails").json()["items"]
    assert scam["important"] and scam["summary"].startswith("Looks like a scam:")


def test_alerts_wait_for_whatsapps_window_then_come_with_your_next_message(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0007intv", **{"from": "HR <hr@corp.com>", "subject": "Interview", "body": "interview on Monday?"})
    wa["closed"] = True
    client.post("/api/emails/check")
    assert get_setting("email_alerts_waiting") and wa["sent"] == []
    wa["closed"] = False
    assert run(inbox.deliver_waiting()) is True
    assert "Interview" in wa["sent"][0]["text"]["body"] and get_setting("email_alerts_waiting") == []


def test_watching_can_be_switched_off_and_needs_gmail(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", "1")
    set_setting("email_watch_enabled", False)
    assert run(inbox.check_inbox(load_registry(), fake_model_provider)) == []
    auth._save("you@example.com", "fake-refresh", SCOPES.replace("https://www.googleapis.com/auth/gmail.readonly ", ""))
    assert client.post("/api/emails/check").status_code == 409


def test_important_emails_go_into_the_briefing(gmail):
    from junior.reports import briefing_prompt

    with session_scope() as s:
        s.add(Email(gmail_id="msg0009", from_name="Sara", subject="Quote", category="client", important=True,
                    summary="Sara wants a quote", received_at=datetime.now(UTC) - timedelta(hours=2)))
    assert "### Important emails in the last 24 hours\n- email 1: Sara wants a quote (from Sara)" in briefing_prompt(all_settings())


def test_junior_muneer_has_the_gmail_tools():
    from junior.agent.tools import TOOL_FACTORIES

    names = [t.name for t in TOOL_FACTORIES["google"]()]
    assert {"gmail_search", "gmail_read", "gmail_draft"} <= set(names)
    assert "email_sorter" in load_registry().names()
