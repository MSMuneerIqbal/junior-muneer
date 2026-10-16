"""P5-02: the Upwork and Fiverr playbooks, and their red lines in the Checker and on the cards."""

import json

import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message
from junior.approvals import create_item
from junior.main import create_app
from junior.playbooks import load_playbooks
from junior.writing.redlines import red_lines
from junior.writing.style import lint


def test_upwork_and_fiverr_playbooks():
    books = load_playbooks()
    assert books["upwork"].max_chars == 5000 and books["upwork"].hashtags == (0, 0)
    assert books["fiverr"].max_chars == 2500
    assert "first 2–3 lines" in books["upwork"].text
    assert "No contact or payment outside Upwork" in books["upwork"].text
    assert "Never share an email address" in books["fiverr"].text


@pytest.mark.parametrize(
    ("text", "platform", "words"),
    [
        ("Email me at muneer@example.com", "upwork", "email address"),
        ("Call me on +92 304 5820729", "upwork", "phone number"),
        ("Let's talk on WhatsApp", "upwork", "WhatsApp"),
        ("Add me on Telegram please", "fiverr", "Telegram"),
        ("I accept PayPal", "upwork", "PayPal"),
        ("Send it to my JazzCash", "fiverr", "JazzCash"),
        ("Payment via bank transfer works", "upwork", "pay"),
        ("We can continue outside Upwork", "upwork", "outside Upwork"),
        ("Pay me directly and save fees", "fiverr", "outside Fiverr"),
        ("See my work at https://github.com/me", "fiverr", "leads off Fiverr"),
        ("Leave 5 stars and I'll give you a discount", "fiverr", "for a review"),
    ],
)
def test_red_lines_are_caught(text, platform, words):
    problems = red_lines(text, platform)
    assert problems and any(words in p for p in problems), problems


@pytest.mark.parametrize(
    "text",
    [
        "Here's my GitHub: https://github.com/MSMuneerIqbal",  # portfolio links are fine on Upwork
        "I can deliver in 5 days for $500, starting 2026-10-20, for 10,000 users.",
        "IMO the signal is strong; I'll zoom in on the data.",
        "I built a crypto exchange dashboard and bank account linking for a fintech app.",
        "Happy to discuss on a call through Upwork, or message me on Upwork anytime.",
    ],
)
def test_ordinary_proposals_are_not_flagged(text):
    assert red_lines(text, "upwork") == []


def test_other_platforms_have_no_freelance_red_lines():
    assert red_lines("Email me at muneer@example.com", "linkedin") == []


def test_red_lines_are_hints_for_the_checker():
    issues = lint("Sure, WhatsApp me and we'll start.", load_playbooks()["upwork"], "message")
    assert any("WhatsApp" in i for i in issues)


# ---- the writing team can't pass a draft that breaks a red line ---------------------------


def j(**kw):
    return [assistant_message(json.dumps(kw))]


def test_a_proposal_that_breaks_a_red_line_never_passes(client):
    import asyncio

    from junior.agent.context import TurnContext
    from junior.agent.helpers import HelperRunner
    from junior.agent.tools import write_draft_for
    from junior.registry import load_registry
    from junior.settings_store import all_settings

    bad = "I can build it. WhatsApp me on +92 304 5820729."
    model = ScriptedModel(
        [
            j(text=bad, image_idea="", missing_facts=[]),
            j(score=9, passes=True, issues=[], invented_facts=[]),  # the Checker missed it...
            j(text=bad, image_idea="", missing_facts=[]),
            j(score=9, passes=True, issues=[], invented_facts=[]),
            j(text=bad, image_idea="", missing_facts=[]),
            j(text="I can build your clinic chatbot. Happy to talk here on Upwork.", changes=["Kept it on Upwork"]),
            j(score=9, passes=True, issues=[], invented_facts=[]),
        ]
    )
    client.put("/api/profile", json={"headline": "AI engineer", "proof": ["Built chatbots"]})
    context = TurnContext(conversation_id=None, settings=all_settings())
    context.helpers = HelperRunner(load_registry(), lambda _n: model)
    result = asyncio.run(write_draft_for(context, "upwork", "proposal", "the clinic chatbot job"))
    assert result.startswith("Written by the team")

    steps = [e for e in context.pending_events if e["type"] == "step"]
    labels = [s["label"] for s in steps]
    assert labels.count("Checker: 9/10, sent back") == 2  # ...but code sent it back anyway
    notes = next(s for s in steps if s["label"] == "Checker: 9/10, sent back")["notes"]
    assert any("WhatsApp" in n for n in notes) and any("phone number" in n for n in notes)
    assert labels[-1] == "Final check: 9/10, ready"  # passes once the red lines are gone
    card = next(e for e in context.pending_events if e["type"] == "approval")["item"]
    assert card["platform"] == "upwork" and card["kind"] == "copy" and card["item_type"] == "proposal"
    assert card["red_lines"] == [] and "WhatsApp" not in card["text"]


# ---- the cards warn, even after your own edits ---------------------------------------------


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


def test_cards_show_red_lines_and_follow_your_edits(client):
    item = create_item(kind="copy", platform="upwork", item_type="message", text="Sure! Let's talk on Upwork.")
    assert client.get(f"/api/approvals/{item.id}").json()["red_lines"] == []
    edited = client.patch(f"/api/approvals/{item.id}", json={"text": "Sure! Email me at me@example.com"}).json()
    assert any("email address" in r for r in edited["red_lines"])
    fixed = client.patch(f"/api/approvals/{item.id}", json={"text": "Sure! Let's keep talking here."}).json()
    assert fixed["red_lines"] == []
