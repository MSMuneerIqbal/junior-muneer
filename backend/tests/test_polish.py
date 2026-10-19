"""The Polisher: emails, docs and messages read like a careful human wrote them, and never lose a fact."""

import asyncio

from junior.agent.context import TurnContext
from junior.writing.polish import MIN_CHARS, Polished, ai_signs, lost_facts, polish, safe_fixes

DRAFT = (
    "Hi Sara,\n\nI hope this email finds you well. I wanted to reach out to delve into the report — it's due on "
    "12 Nov and costs $450. Details: https://example.com/report?id=7. Moreover, ping me at muneer@example.com.\n\nMuneer"
)
CLEAN = (
    "Hi Sara,\n\nQuick note about the report. It's due on 12 Nov and costs $450. Details: "
    "https://example.com/report?id=7. You can reach me at muneer@example.com.\n\nMuneer"
)


class Helpers:
    """A stand-in Polisher that answers from a script."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    async def run_structured(self, agent, prompt, context, output_type):
        assert agent == "polisher" and output_type is Polished
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Polished(text=answer, changes=["simpler words"])


def context_with(helpers) -> TurnContext:
    context = TurnContext(conversation_id=None, settings={})
    context.helpers = helpers
    return context


def run(coro):
    return asyncio.run(coro)


def test_ai_signs_are_found_in_code():
    signs = ai_signs(DRAFT)
    assert {'"i hope this email finds you well"', '"i wanted to reach out"', '"delve"', '"moreover"', "long dashes"} <= set(signs)
    assert "emojis" in ai_signs("Done 🎉") and '"not just X, but Y"' in ai_signs("It's not just fast, but cheap.")
    assert ai_signs(CLEAN) == []


def test_safe_fixes_and_facts():
    assert safe_fixes("Fast — and cheap 🚀 now") == "Fast, and cheap now"
    assert lost_facts(DRAFT, CLEAN) == []
    assert lost_facts(DRAFT, CLEAN.replace("$450", "$500")) == ["450"]
    assert lost_facts(DRAFT, CLEAN.replace("https://example.com/report?id=7", "the link")) == ["https://example.com/report?id=7"]


def test_a_clean_rewrite_is_used_and_shown_in_show_work():
    helpers = Helpers(CLEAN)
    context = context_with(helpers)
    assert run(polish(DRAFT, "an email", context)) == CLEAN
    [step] = context.pending_events
    assert step["label"] == "Polisher: made the an email read like you wrote it" or step["label"].startswith("Polisher: made the")
    assert "## What it is\nan email" in helpers.prompts[0]


def test_leftover_ai_signs_get_one_more_try():
    helpers = Helpers(CLEAN.replace("Quick note", "Moreover, a quick note"), CLEAN)
    assert run(polish(DRAFT, "an email", context_with(helpers))) == CLEAN
    assert '"moreover"' in helpers.prompts[1]


def test_a_rewrite_that_changes_a_fact_is_never_used():
    wrong = CLEAN.replace("$450", "$500")
    helpers = Helpers(wrong, wrong)
    out = run(polish(DRAFT, "an email", context_with(helpers)))
    assert "$450" in out and "$500" not in out  # your draft, with only safe fixes
    assert "—" not in out and "you dropped 450" in helpers.prompts[1]


def test_short_text_or_a_failing_polisher_keeps_your_words():
    assert run(polish("OK, done — thanks!", "a message", context_with(Helpers()))) == "OK, done, thanks!"
    assert len("OK, done") < MIN_CHARS
    assert run(polish(DRAFT, "an email", context_with(Helpers(RuntimeError("down"))))) == safe_fixes(DRAFT)
