"""P5-07: you paste a client conversation, the team drafts a reply, you copy and send it yourself."""

import json

import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message, chunked_answer, function_call
from junior.freelance.messages import client_warnings
from junior.freelance.scam import scam_signs
from junior.main import create_app

NL = chr(10)
ROOM = "https://www.upwork.com/ab/messages/rooms/room_abc"
CONVO = NL.join(
    [
        "Sarah K.  10:02 AM",
        "Hi Muneer, thanks for applying. Can you add Urdu voice replies to the clinic bot?",
        "Muneer Iqbal  10:15 AM",
        "Hi Sarah, yes, voice replies are possible. How many patients use it each day?",
        "Sarah K.  10:20 AM",
        "About 200 a day. What would you charge for the voice part?",
    ]
)
OFF_PLATFORM = CONVO + NL + "Let's continue on WhatsApp, my number is +971 50 123 4567."
REPLY = "Thanks, Sarah. For 200 patients a day, voice replies fit well. Could you share two sample questions so I can scope it?"


def j(**kw):
    return [assistant_message(json.dumps(kw))]


def team():
    return [
        j(text=REPLY, missing_facts=[]),
        j(score=9, passes=True, issues=[], invented_facts=[]),
        j(text=REPLY, changes=[]),
        j(score=9, passes=True, issues=[], invented_facts=[]),
    ]


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def client(model):
    with TestClient(create_app(model_provider=lambda: (lambda _name: model))) as c:
        c.put("/api/profile", json={"headline": "AI engineer", "proof": ["Built a hospital assistant with 47 tools"]})
        yield c


def reply_to(client, model, text):
    model.extend(
        [
            [function_call("freelance", {"request": "Reply to this client"}, call_id="f1")],
            [function_call("write_draft", {"platform": "upwork", "item_type": "reply", "request": "a reply to Sarah"}, call_id="w1")],
            *team(),
            [assistant_message("The reply card is ready.")],
            chunked_answer("Your reply to Sarah is ready to copy."),
        ]
    )
    paste = {"text": text, "platform": "upwork", "kind": "client_message", "source_url": ROOM}
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": "Reply to this client", "paste": paste})
        events = []
        while events[-1:] == [] or events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())
    return events


def prompt_of(model, who):
    return next(c.input[-1]["content"] for c in model.calls if who in (c.system_instructions or ""))


def test_a_reply_answers_the_clients_newest_message(client, model):
    events = reply_to(client, model, CONVO)
    labels = [s["label"] for s in events[-1]["steps"]]
    assert "Warning signs in the client's message" not in labels  # nothing to warn about

    # The Writer knows it's a conversation, and sees it fenced as someone else's words.
    writer = prompt_of(model, "You are the Writer")
    assert "Messages from Muneer are already sent: answer the client's newest message" in writer
    assert "START OF THEIR TEXT" in writer and "What would you charge for the voice part?" in writer

    card = next(e for e in events if e["type"] == "approval")["item"]
    assert card["platform"] == "upwork" and card["item_type"] == "reply" and card["kind"] == "copy"
    assert card["open_url"] == ROOM  # "Open the conversation"
    assert card["from_outside"] is True and card["status"] == "waiting"  # always waits for you
    assert "warnings" not in card["meta"] and card["red_lines"] == []

    client.post(f"/api/approvals/{card['id']}/posted")  # you sent it on Upwork
    assert client.get(f"/api/approvals/{card['id']}").json()["status"] == "posted"


def test_warning_signs_in_a_client_message_are_flagged_by_code(client, model):
    events = reply_to(client, model, OFF_PLATFORM)
    step = next(s for s in events[-1]["steps"] if s["label"] == "Warning signs in the client's message")
    assert "Asks to talk outside the platform (on an app)." in step["notes"]
    assert "Contains a phone number." in step["notes"]

    # The Freelance Manager is told, and the Writer must keep it on Upwork.
    manager = next(c.input[0]["content"] for c in model.calls if "Freelance Manager for Upwork" in (c.system_instructions or ""))
    assert "## Warning signs code found in the client's message" in manager
    assert "Politely keep everything on Upwork" in prompt_of(model, "You are the Writer")

    card = next(e for e in events if e["type"] == "approval")["item"]
    assert "Contains a phone number." in card["meta"]["warnings"]
    assert card["red_lines"] == []  # the reply itself keeps to Upwork's rules


def message(text):
    return {"text": text, "platform": "upwork", "kind": "client_message"}


@pytest.mark.parametrize(
    "text, sign",
    [
        ("It's easier to talk on WhatsApp, can you message me?", "Mentions WhatsApp: if they want to talk, share files or pay there, keep it on Upwork."),
        ("Can we do a Zoom call tomorrow?", "Asks to talk outside the platform (on an app)."),
        ("Also, do you have Skype?", "Mentions Skype"),
        ("Let’s move this to Telegram.", "Asks to talk outside the platform (on an app)."),  # curly apostrophe
        ("Send the files to anna.k@studio-mail.com please.", "Gives an email address to contact them outside the platform."),
    ],
)
def test_warning_signs_in_client_messages(text, sign):
    warnings = client_warnings(message(text))
    assert any(w.startswith(sign) for w in warnings), warnings
    assert len([w for w in warnings if "outside the platform (on an app)" in w or w.startswith("Mentions")]) <= 1  # said once


@pytest.mark.parametrize(
    "text",
    [
        "The signal is weak here, so I'll reply properly tonight.",
        "Can we zoom in on the delivery dates in the plan?",
        "Thanks! The demo looks great. Can you add a returns flow?",
    ],
)
def test_ordinary_client_messages_have_no_warnings(text):
    assert client_warnings(message(text)) == []


def test_a_job_about_whatsapp_bots_is_still_not_a_scam():
    assert scam_signs("Our customers prefer to chat on WhatsApp, so the bot must answer there.") == []


def test_only_upwork_and_fiverr_client_messages_are_checked():
    text = "Message me on WhatsApp."
    assert client_warnings({"text": text, "platform": "fiverr", "kind": "client_message"})
    assert client_warnings({"text": text, "platform": "upwork", "kind": "job"}) == []  # jobs have their own check
    assert client_warnings({"text": text, "platform": "linkedin", "kind": "client_message"}) == []
    assert client_warnings(None) == []
