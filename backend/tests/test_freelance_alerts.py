"""P5-03 / P4-05: Upwork and Fiverr notification emails. Client messages are checked for scam signs and alerted with
"paste the whole chat"; job alerts are read, scored and saved; Fiverr orders are saved with reminders; anything
unclear is shown with the email itself. Nothing is ever sent to a client."""

import asyncio
from datetime import UTC, datetime, timedelta

from junior.freelance import alerts
from junior.freelance.alerts import client_words, kind_of, message_warnings
from junior.settings_store import set_setting
from test_gmail import gmail  # noqa: F401 - pretend Gmail and WhatsApp

# His real Fiverr notification (2026-10-17), names kept, the link left out.
FIVERR_BODY = """1 new messages for you

Hi muneeriqbal729,

cole919b messaged you:

Everything is done on my end. Now I'm just waiting for you. Please take a look and review the details of the order I just placed with you: "[View link on Fiverr]

Go to your inbox

This email was intended for muneeriqbal729, because you signed up for Fiverr | Unsubscribe"""


def mail(sender: str, subject: str, body: str = "", labels=None) -> dict:
    return {"from_address": sender, "subject": subject, "body": body, "labels": labels or ["INBOX"]}


def test_which_emails_are_upwork_or_fiverr_ones():
    assert kind_of(mail("noreply@e.fiverr.com", "You’ve got new messages from cole919b")) == "fiverr_message"
    assert kind_of(mail("noreply@e.fiverr.com", "You've received an order from sara_k")) == "fiverr_order"
    assert kind_of(mail("donotreply@upwork.com", "You have unread messages")) == "upwork_message"
    assert kind_of(mail("donotreply@upwork.com", "New jobs matching your saved search \"AI agent\"")) == "upwork_jobs"
    assert kind_of(mail("upwork@email.upwork.com", "Why top freelancers choose Freelancer Plus")) is None  # an ad
    assert kind_of(mail("noreply@upwork.com", "Update to our User Agreement and Privacy Policy")) is None
    assert kind_of(mail("noreply@e.fiverr.com", "New messages", labels=["INBOX", "CATEGORY_PROMOTIONS"])) is None
    assert kind_of(mail("ali@fiverr-help.example", "You've got new messages from x")) is None  # not Fiverr's own address


def test_the_clients_words_and_the_fake_order_trick():
    words = client_words(FIVERR_BODY)
    assert words.startswith("Everything is done on my end.") and "Go to your inbox" not in words
    [sign] = message_warnings(words)
    assert "placed an order" in sign and "never open links" in sign
    assert message_warnings("Hi, can you build a RAG chatbot for my clinic? Budget $300.") == []


def test_the_other_scam_wordings_from_his_inbox():
    """All four real messages of 13-17 Oct 2026 were the same scam in different words."""
    for text in (
        "Hello! I have already placed my order for your service and am currently awaiting your approval. Please find the link here",
        "Hello I have placed the order, please check the details and confirm",
    ):
        assert any("placed an order" in s for s in message_warnings(text)), text
    rushed = message_warnings("Hello I'm interested in your gig. I've been waiting for quite a long time, hurry up please, "
                              "I've attached the document")
    assert rushed and "Rushes you" in rushed[0]
    body = ("4 new messages for you Hi muneeriqbal729, viperatomic737 left you messages in regards to the Gig, I will build "
            "an ai chatbot for your website trained on your own data: Hello I have placed the order Go to your inbox")
    assert client_words(body) == "Hello I have placed the order"


def test_a_fiverr_message_alerts_you_with_its_warning_and_how_to_reply(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0010fiverr", **{"from": "Fiverr <noreply@e.fiverr.com>",
                                            "subject": "You’ve got new messages from cole919b", "body": FIVERR_BODY})
    assert client.post("/api/emails/check").json() == {"new": 1}
    [row] = client.get("/api/emails").json()["items"]
    assert row["category"] == "client" and row["important"]
    assert row["summary"].startswith("Fiverr message from cole919b: “Everything is done on my end.")
    assert "⚠" in row["summary"] and "paste the whole conversation" in row["summary"]
    [alert] = wa["sent"]
    assert "cole919b" in alert["text"]["body"] and "never open links" in alert["text"]["body"]


def test_an_upwork_job_alert_is_read_scored_and_saved(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0011jobs", **{"from": "Upwork <donotreply@upwork.com>", "subject": "New jobs for \"AI agent\"",
                                         "body": "Job: Build an AI agent for a clinic\n...\nJob: Data entry in Excel\n..."})
    client.post("/api/emails/check")
    jobs = {j["title"]: j for j in client.get("/api/jobs?status=all").json()}
    assert jobs["Build an AI agent for a clinic"]["score"] == 8 and jobs["Build an AI agent for a clinic"]["url"].startswith("https://www.upwork.com/jobs/")
    assert jobs["Data entry in Excel"]["verdict"] == "skip"
    [row] = client.get("/api/emails").json()["items"]
    assert row["category"] == "freelance" and row["important"] and "1 worth applying" in row["summary"]
    assert "write the proposal for job" in row["summary"]
    assert "Build an AI agent" in wa["sent"][0]["text"]["body"]


def test_a_job_alert_with_no_good_fits_doesnt_bother_you(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0012jobs", **{"from": "Upwork <donotreply@upwork.com>", "subject": "New job: Data entry",
                                         "body": "Job: Data entry in Excel\n..."})
    client.post("/api/emails/check")
    [row] = client.get("/api/emails").json()["items"]
    assert not row["important"] and "none a strong fit" in row["summary"] and wa["sent"] == []


def test_an_unreadable_alert_is_shown_as_it_is(gmail):
    client, _, google, _ = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0013odd", **{"from": "Upwork <donotreply@upwork.com>", "subject": "Your jobs this week", "body": "no list here"})
    client.post("/api/emails/check")
    [row] = client.get("/api/emails").json()["items"]
    assert row["important"] and "couldn't read jobs from" in row["summary"] and "paste a job here" in row["summary"]


def test_a_fiverr_order_email_becomes_an_order(gmail):
    client, _, google, _ = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0014order", **{"from": "Fiverr <noreply@e.fiverr.com>", "subject": "You've received an order from sara_k",
                                          "body": "You've received an order from sara_k. Order #FO123. Gig: RAG chatbot."})
    client.post("/api/emails/check")
    [order] = client.get("/api/orders?status=open").json()
    assert order["buyer"] == "sara_k" and order["platform"] == "fiverr"
    [row] = client.get("/api/emails").json()["items"]
    assert row["summary"].startswith(f"Fiverr order {order['id']}:") and row["important"]


def test_the_reader_is_never_given_tools():
    from junior.registry import load_registry

    reader = load_registry().get("freelance_reader")
    assert reader.tools == () and reader.action_types == ()


def test_nothing_is_ever_sent_to_a_client(gmail):
    client, _, google, wa = gmail
    set_setting("email_watch_since", str(int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())))
    google.add_mail(id="msg0015fiverr", **{"from": "Fiverr <noreply@e.fiverr.com>",
                                            "subject": "You’ve got new messages from ali", "body": "ali messaged you:\n\nHi!\n\nGo to your inbox"})
    client.post("/api/emails/check")
    assert google.sent == [] and google.drafts == {}  # alerts only reach you
    assert client.get("/api/approvals?status=all").json() == []
