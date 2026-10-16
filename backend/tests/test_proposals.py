"""Proposals: only the text to paste, screening answers in their own boxes, and the length guide."""

import asyncio
import json

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message
from junior.agent.context import TurnContext
from junior.agent.helpers import HelperRunner
from junior.agent.tools import write_draft_for
from junior.main import create_app
from junior.playbooks import load_playbooks
from junior.registry import load_registry
from junior.settings_store import all_settings
from junior.writing.style import leftover_notes, lint, undersells
from junior.writing.team import Answer, fit_answers

NL = chr(10)
COVER = "Your clinic needs a chatbot that books visits. I built a hospital assistant with 47 tools. What do patients ask most?"
QUESTION = "Describe a similar project"
ANSWERS = [{"question": QUESTION, "answer": "A hospital assistant with 47 tools over MCP."}]
PASS = {"score": 9, "passes": True, "issues": [], "invented_facts": []}


def j(**kw):
    return [assistant_message(json.dumps(kw))]


def run_team(model, questions=None, times=1, job_id=None):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        c.put("/api/profile", json={"headline": "AI engineer", "proof": ["Built a hospital assistant with 47 tools over MCP"]})
        context = TurnContext(conversation_id=None, settings=all_settings())
        context.helpers = HelperRunner(load_registry(), lambda _n: model)
        results = [
            asyncio.run(
                write_draft_for(context, "upwork", "proposal", "the clinic chatbot job", job_id=job_id, screening_questions=questions)
            )
            for _ in range(times)
        ]
        context.results = results
        return context


def card(context):
    return next(e for e in context.pending_events if e["type"] == "approval")["item"]


def test_notes_left_in_a_proposal_never_pass_and_answers_get_their_own_boxes():
    noted = "APPROVAL CARD: Job 1" + NL + "Status: awaiting approval" + NL + NL + COVER
    model = ScriptedModel(
        [
            j(text=noted, answers=ANSWERS),
            j(**PASS),  # the Checker missed the notes...
            j(text=COVER, answers=ANSWERS),
            j(**PASS),
            j(text=COVER, changes=["Simpler words"]),  # the Humanizer keeps the Writer's answers
            j(**PASS),
        ]
    )
    context = run_team(model, questions=[QUESTION])
    steps = [e for e in context.pending_events if e["type"] == "step"]
    sent_back = next(s for s in steps if s["label"] == "Checker: 9/10, sent back")  # ...code didn't
    assert any("isn't part of the text to paste" in n for n in sent_back["notes"])

    # The Writer was given the client's question; the Checker saw the answer apart from the draft.
    writer = next(c for c in model.calls if "You are the Writer" in (c.system_instructions or ""))
    assert "1. Describe a similar project" in writer.input[-1]["content"]
    checker = next(c for c in model.calls if "You are the Checker" in (c.system_instructions or ""))
    draft, after = checker.input[-1]["content"].split("</draft>", 1)
    assert "Question 1: Describe a similar project" in after and "Describe a similar project" not in draft.split("<draft>")[-1]

    assert card(context)["text"] == COVER  # only the cover letter
    assert card(context)["meta"]["answers"] == ANSWERS


def test_only_answers_to_the_clients_own_questions_are_kept():
    """Your "Should I apply?" isn't a screening question; a reworded question still matches."""
    written = [
        {"question": "Should I apply?", "answer": "Yes, apply."},
        {"question": "Screening answer: describe a similar project.", "answer": "A hospital assistant with 47 tools over MCP."},
    ]
    model = ScriptedModel([j(text=COVER, answers=written), j(**PASS), j(text=COVER, changes=[]), j(**PASS)])
    context = run_team(model, questions=[QUESTION])
    assert card(context)["meta"]["answers"] == ANSWERS


def test_no_screening_questions_means_no_answers():
    model = ScriptedModel(
        [j(text=COVER, answers=[{"question": "Should I apply?", "answer": "Yes."}]), j(**PASS), j(text=COVER, changes=[]), j(**PASS)]
    )
    context = run_team(model)
    writer = next(c for c in model.calls if "You are the Writer" in (c.system_instructions or ""))
    assert "None in this job post: leave `answers` empty" in writer.input[-1]["content"]
    assert "answers" not in card(context)["meta"]


def test_a_screening_question_without_an_answer_is_sent_back():
    model = ScriptedModel(
        [
            j(text=COVER),  # forgot the answer
            j(**PASS),
            j(text=COVER, answers=ANSWERS),
            j(**PASS),
            j(text=COVER, changes=[]),
            j(**PASS),
        ]
    )
    context = run_team(model, questions=[QUESTION])
    sent_back = next(e for e in context.pending_events if e.get("label") == "Checker: 9/10, sent back")
    assert any("Screening question 1 has no answer" in n for n in sent_back["notes"])
    assert card(context)["meta"]["answers"] == ANSWERS and card(context)["meta"]["score"] == 9


def test_one_proposal_card_per_job_in_a_message():
    """A screening answer never gets a card of its own: the second card for the job is refused."""
    model = ScriptedModel([j(text=COVER, answers=ANSWERS), j(**PASS), j(text=COVER, changes=[]), j(**PASS)])
    context = run_team(model, questions=[QUESTION], times=2, job_id=7)
    first, second = context.results
    assert first.startswith("Written by the team")
    assert second.startswith("NOT written: job 7 already has a proposal card")
    assert len(context.approval_ids) == 1


def test_fit_answers():
    q1, q2 = "Describe a similar project", "What is your availability?"
    old = [Answer(question=q2, answer="Full time from Monday.")]
    new = [Answer(question="should i apply", answer="yes"), Answer(question="describe a similar project.", answer="The hospital bot.")]
    assert fit_answers([q1, q2], new, old) == [
        Answer(question=q1, answer="The hospital bot."),
        Answer(question=q2, answer="Full time from Monday."),  # skipped this time: the earlier answer stays
    ]
    assert fit_answers([], new) == []
    assert fit_answers([q1], [Answer(question=q1, answer="  ")]) == []  # an empty answer isn't an answer


def test_underselling_is_flagged():
    assert undersells("These are parts of your scope I’d still need to validate.")
    assert undersells("I haven't used Azure before, but I learn fast.")
    assert undersells("I have no direct experience with Arabic.")
    assert undersells("I'd need to see two sample files first.") == []
    assert undersells("I have noticed your firm works in English and Arabic.") == []
    book = load_playbooks()["upwork"]
    assert any("Undersells you" in i for i in lint("I'm new to RAG but I'll try.", book, "proposal"))


def test_leftover_notes_and_placeholders():
    assert leftover_notes("COVER LETTER" + NL + "Hi") and leftover_notes("Thanks, [your name]")
    assert leftover_notes("Recommendation: apply" + NL + "Hi")
    assert leftover_notes("Hi, I read your job post carefully.") == []
    assert leftover_notes("A note in [optional] brackets") == []


def test_the_proposal_length_guide_is_a_hint():
    book = load_playbooks()["upwork"]
    assert any("Long for a Upwork proposal" in i for i in lint("word " * 400, book, "proposal"))
    assert not any("proposal" in i for i in lint("word " * 180, book, "proposal"))
