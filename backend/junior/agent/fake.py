"""Fake AI for trying the dashboard without an API key (FAKE_AI=true). No network, no cost.

It echoes your message, streamed in small pieces. Two tricks to see the UI work:
  - a message containing "search" calls the web_search tool, and the web
    researcher does a (pretend) hosted search;
  - a message starting with "remember " saves the rest as a memory, through the
    real save_memory tool and its safety checks;
  - a message starting with "draft " puts the rest in the approval queue as a
    LinkedIn post (a card under the answer);
  - a message starting with "write " goes to the Social Media Manager, who runs the
    real writing team pipeline (fake Writer, Checker and Humanizer) for a LinkedIn post;
  - a message starting with "ideas" makes the manager save 3 fake content ideas.
"""

import asyncio
import re
import copy
import json
from collections.abc import AsyncIterator
from typing import Any

from agents import Model, ModelResponse, Usage, WebSearchTool
from agents.testing import ModelStep, assistant_message, function_call
from agents.testing.model import _stream_events_for_step
from openai.types.responses import (
    ResponseFunctionWebSearch,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_function_web_search import ActionSearch
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

CHUNK = 6
DELAY_SECONDS = 0.03


def _usage(text_in: str, text_out: str) -> Usage:
    i, o = max(len(text_in) // 4, 1), max(len(text_out) // 4, 1)
    return Usage(
        requests=1,
        input_tokens=i,
        output_tokens=o,
        total_tokens=i + o,
        input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )


NL = chr(10)

def _last_user_text(items: Any) -> str:
    if isinstance(items, str):
        return items
    for item in reversed(items):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            return content if isinstance(content, str) else json.dumps(content)
    return ""


class FakeModel(Model):
    def _fake_freelance(self, input: Any, brief: str) -> list[Any]:
        """The Freelance Manager: score a pasted job, then write the proposal; or reply to a client."""
        outputs = [
            i.get("output", "") for i in (input if isinstance(input, list) else [])
            if isinstance(i, dict) and i.get("type") == "function_call_output"
        ]
        their = ""
        if "START OF THEIR TEXT" in brief:
            their = brief.split("START OF THEIR TEXT", 1)[1].split("END OF THEIR TEXT", 1)[0].strip("= \n")
        if not outputs:
            if not their:
                return [assistant_message("(fake Freelance Manager) Paste the job post with the Paste box first.")]
            if "(a job from" in brief:
                score = {
                    "title": their.splitlines()[0][:80],
                    "budget": "",
                    "skills": ["Python"],
                    "score": 8,
                    "verdict": "apply",
                    "reasons": ["(fake) Matches your skills"],
                    "concerns": [],
                }
                return [function_call("score_job", {"score": score}, call_id="fake-score")]
            earlier = re.search(r"## Job (\d+) as they pasted it earlier", brief)
            if earlier:
                args = {"platform": "upwork", "item_type": "proposal", "request": "a proposal for this job", "job_id": int(earlier.group(1))}
                return [function_call("write_draft", args, call_id="fake-proposal")]
            if "(an order from" in brief:
                return [function_call("save_order", {"order": _fake_order(their)}, call_id="fake-order")]
            platform = "fiverr" if "from fiverr" in brief else "upwork"
            args = {"platform": platform, "item_type": "reply", "request": "a reply to this client"}
            return [function_call("write_draft", args, call_id="fake-reply")]
        latest = outputs[-1]
        saved = re.match(r"Saved as job (\d+)", latest)
        asked = brief.split("\n", 2)[1].lower() if brief.count("\n") >= 1 else ""  # the request, not the job lists
        if saved and "Marked skip" not in latest and "proposal" in asked:
            args = {"platform": "upwork", "item_type": "proposal", "request": "a proposal for this job", "job_id": int(saved.group(1))}
            questions = [
                line.split(":", 1)[1].strip() for line in their.splitlines() if line.lower().startswith("screening question:")
            ]
            if questions:
                args["screening_questions"] = questions
            return [function_call("write_draft", args, call_id="fake-proposal")]
        order = re.match(r"Saved as order (\d+)", latest)
        request = brief.split("\n", 2)[1] if brief.count("\n") >= 1 else ""
        if order and "deliver" in request.lower():
            args = {
                "platform": "fiverr",
                "item_type": "delivery",
                "request": "the delivery message for this order",
                "notes": "(fake) The files are delivered.",
                "order_id": int(order.group(1)),
            }
            return [function_call("write_draft", args, call_id="fake-delivery")]
        return [assistant_message(f"(fake Freelance Manager) {latest}")]

    def _plan(self, input: Any, tools: list[Any]) -> tuple[list[Any], bool]:
        """What to answer: (output items, include a hosted web search)."""
        hosted_search = any(isinstance(t, WebSearchTool) for t in tools)
        tool_names = {getattr(t, "name", "") for t in tools if not isinstance(t, WebSearchTool)}
        text = _last_user_text(input)
        if text.startswith("## Question from"):
            # A news agent answering from the digest: quote its first item with its link.
            first = next((line[2:] for line in text.splitlines() if line.startswith("- ")), "")
            return [assistant_message(f"(fake news agent) From today's digest: {first or 'nothing yet.'}")], False
        if hosted_search:
            # The web researcher: pretend to search, then report.
            return [assistant_message(f"- (fake search result for: {text})")], True
        if text.startswith("## Request from") and "score_job" in tool_names:
            return self._fake_freelance(input, text), False
        last = input[-1] if isinstance(input, list) and input else None
        if text.startswith("## Morning briefing facts"):
            needs = next((ln[2:] for ln in text.splitlines() if ln.startswith("- Waiting for your OK")), "Nothing needs you yet.")
            return [assistant_message(f"(fake AI) Good morning! {needs}")], False
        if "what happened" in text.lower() and "what_happened" in tool_names:
            said = last.get("output", "") if isinstance(last, dict) and last.get("type") == "function_call_output" else ""
            if not said:
                return [function_call("what_happened", {"period": "today"}, call_id="fake-report")], False
            facts = said.split("(These facts", 1)[0].strip()
            return [assistant_message(f"(fake AI) Here's your day:{NL}{NL}{facts}")], False
        if text.startswith("[Background task"):
            asked = text.split(": ", 1)[1].splitlines()[0] if ": " in text else text
            return [assistant_message(f"(fake AI) Finished in the background: {asked}")], False
        if text.lower().startswith("in background:") and "run_in_background" in tool_names:
            said = last.get("output", "") if isinstance(last, dict) and last.get("type") == "function_call_output" else ""
            if not said:
                asked = text[len("in background:"):].strip()
                return [function_call("run_in_background", {"title": asked[:40], "request": asked}, call_id="fake-bg")], False
            return [assistant_message("(fake AI) I'm on it in the background. Keep chatting; the result will appear here.")], False
        if text.lower().startswith("do these:") and "update_plan" in tool_names:
            # A request with several parts: show the checklist, then tick every part off.
            parts = [p.strip() for p in text[len("do these:"):].split(";") if p.strip()]
            said = last.get("output", "") if isinstance(last, dict) and last.get("type") == "function_call_output" else ""
            if not said:
                items = [{"text": p, "status": "pending"} for p in parts]
                return [function_call("update_plan", {"items": items}, call_id="fake-plan-1")], False
            if said.startswith("Checklist shown: 0 of"):
                items = [{"text": p, "status": "done"} for p in parts]
                return [function_call("update_plan", {"items": items}, call_id="fake-plan-2")], False
            return [assistant_message(f"(fake AI) All {len(parts)} parts done.")], False
        if isinstance(last, dict) and last.get("type") == "function_call_output":
            return [assistant_message(f"(fake AI) Tool said: {last.get('output')}")], False
        if "search" in text.lower() and "web_search" in tool_names:
            return [function_call("web_search", {"query": text}, call_id="fake-search")], False
        if text.lower().startswith("email me ") and "email_me" in tool_names:
            words = text[len("email me ") :].strip()
            args = {"subject": f"From Junior Muneer: {words[:60]}", "body": f"(fake AI) {words}", "your_words": text}
            return [function_call("email_me", args, call_id="fake-email")], False
        if text.lower().startswith("remember "):
            words = text[len("remember ") :].strip()
            return [
                function_call(
                    "save_memory", {"fact": words, "your_words": words}, call_id="fake-mem"
                )
            ], False
        if text.startswith("## Request from") and "save_ideas" in tool_names:
            # The Social Media Manager: ideas, or a draft through the writing team.
            request = text.split("\n", 2)[1]
            if request.lower().startswith("ideas"):
                ideas = [
                    {"platform": "linkedin", "title": f"Fake idea {n}: {request[6:].strip()}", "angle": "A real lesson", "kind": "lesson"}
                    for n in (1, 2, 3)
                ]
                return [function_call("save_ideas", {"ideas": ideas}, call_id="fake-ideas")], False
            topic = request[len("write ") :].strip() if request.lower().startswith("write ") else request
            args = {"platform": "linkedin", "item_type": "post", "request": topic}
            idea = re.match(r"idea (\d+)$", topic, re.IGNORECASE)
            if idea:
                args["idea_id"] = int(idea.group(1))
            return [function_call("write_draft", args, call_id="fake-write")], False
        lowered = text.lower()
        if "ai news" in lowered and "ai_news" in tool_names:
            return [function_call("ai_news", {"question": text}, call_id="fake-ai-news")], False
        if "pakistan" in lowered and ("news" in lowered or "trending" in lowered) and "pakistan_news" in tool_names:
            return [function_call("pakistan_news", {"question": text}, call_id="fake-pk-news")], False
        if "freelance" in tool_names and any(w in lowered for w in ("proposal", "should i apply", "upwork", "fiverr", "client", "order")):
            return [function_call("freelance", {"request": text}, call_id="fake-freelance")], False
        if text.lower().startswith(("write ", "ideas")) and "social_media" in tool_names:
            return [function_call("social_media", {"request": text}, call_id="fake-social")], False
        if text.lower().startswith("draft ") and "add_to_approvals" in tool_names:
            words = text[len("draft ") :].strip()
            platform = "linkedin"
            if words.lower().startswith("facebook "):  # "draft facebook ..." -> the (fake) connected Page
                platform, words = "facebook", words[len("facebook ") :].strip()
            return [
                function_call(
                    "add_to_approvals",
                    {"platform": platform, "item_type": "post", "text": words},
                    call_id="fake-draft",
                )
            ], False
        reply = (
            "(fake AI) You said:\n\n"
            f"> {text}\n\n"
            "Add your OpenAI key to `backend/.env` and turn `FAKE_AI` off for real answers."
        )
        return [assistant_message(reply)], False

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs) -> ModelResponse:  # noqa: E501
        if output_schema is not None and not output_schema.is_plain_text():
            answer = _team_answer(output_schema.name(), _last_user_text(input))
            await asyncio.sleep(0.4)  # long enough to watch the steps arrive
            output = [assistant_message(json.dumps(answer))]
            return ModelResponse(output=output, usage=_usage(str(input), str(output)), response_id="fake")
        output, _ = self._plan(input, tools)
        return ModelResponse(output=output, usage=_usage(str(input), str(output)), response_id="fake")

    async def stream_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs) -> AsyncIterator[Any]:  # noqa: E501
        output, with_search = self._plan(input, tools)
        if _last_user_text(input).startswith("[Background task"):
            await asyncio.sleep(2)  # long enough to see "Working on it in the background"
        step = ModelStep(output=output, usage=_usage(str(input), str(output)))
        events = _stream_events_for_step(step, preserve_raw_usage=False)
        if with_search:
            search = ResponseFunctionWebSearch(
                id="fake-ws",
                status="completed",
                type="web_search_call",
                action=ActionSearch(type="search", query=_last_user_text(input)[:60]),
            )
            running = search.model_copy(update={"status": "in_progress"})
            events[-1].response.output = [search, *events[-1].response.output]
            events = events[:2] + [
                ResponseOutputItemAddedEvent(
                    type="response.output_item.added", item=running, output_index=0, sequence_number=0
                ),
                ResponseOutputItemDoneEvent(
                    type="response.output_item.done", item=search, output_index=0, sequence_number=0
                ),
            ] + events[2:]
        for event in events:
            if isinstance(event, ResponseTextDeltaEvent):
                for i in range(0, len(event.delta), CHUNK):
                    piece = copy.copy(event)
                    piece.delta = event.delta[i : i + CHUNK]
                    await asyncio.sleep(DELAY_SECONDS)
                    yield piece
            else:
                if isinstance(event, ResponseOutputItemDoneEvent) and with_search:
                    await asyncio.sleep(0.6)  # long enough to see "Searching the web…"
                yield event


def _fake_order(their: str) -> dict:
    """A fake reading of a pasted order: the title from its first line, the due time from 'Due in N hours'."""
    from datetime import UTC, datetime, timedelta

    from junior.settings_store import get_setting
    from junior.timeutil import zone

    hours = re.search(r"due in (\d+) hours?", their, re.IGNORECASE)
    due = ""
    if hours:
        local = datetime.now(UTC).astimezone(zone(get_setting("timezone"))) + timedelta(hours=int(hours.group(1)))
        due = local.strftime("%Y-%m-%d %H:%M")
    number = re.search(r"#(FO[A-Z0-9]+)", their)
    return {
        "number": number.group(1) if number else "",
        "buyer": "(fake) buyer",
        "title": their.splitlines()[0][:80],
        "price": "$50",
        "due": due,
        "revisions_included": 2,
        "revisions_used": 0,
        "status": "active",
        "requirements": ["(fake) What the buyer asked for"],
    }


def _team_answer(schema: str, prompt: str) -> dict:
    """Fake Writer, Checker and Humanizer answers (structured, like the real ones)."""
    request = next((line[len("Request: "):] for line in prompt.splitlines() if line.startswith("Request: ")), "")
    if "DigestIn" in schema:
        return _fake_digest(prompt)
    if "TidyOut" in schema:
        return _fake_tidy(prompt)
    if "Draft" in schema:
        who = "(fake Writer, revised)" if "## The Checker sent it back" in prompt else "(fake Writer)"
        listed = prompt.split("## Screening questions (", 1)[1].split("\n## ", 1)[0] if "## Screening questions (" in prompt else ""
        return {
            "text": f"{who} A short post about {request}. Here's what I built and one thing I learned.\n\n#AI #MCP #Python",
            "image_idea": "A screenshot of the app",
            "missing_facts": [],
            "answers": [
                {"question": q, "answer": f"(fake Writer) A short, true answer to: {q}"}
                for q in re.findall(r"^\d+\. (.+)$", listed, re.MULTILINE)
            ],
        }
    if "Review" in schema:
        draft = prompt.split("<draft>\n", 1)[-1]
        if "revised" in draft or "Humanizer" in draft:
            return {"score": 9, "passes": True, "invented_facts": [], "issues": []}
        return {"score": 6, "passes": False, "invented_facts": [], "issues": ["Make the first line about the result."]}
    draft = prompt.split("<draft>\n", 1)[-1].split("\n</draft>", 1)[0]
    text = draft.replace("(fake Writer, revised)", "(fake Humanizer)").replace("(fake Writer)", "(fake Humanizer)")
    return {"text": text, "changes": ["Simpler words"]}


def _fake_tidy(prompt: str) -> dict:
    """The fake memory tidier: archives exact duplicates (same words), keeping the first."""
    first: dict[str, int] = {}
    picks = []
    for m in re.finditer(r"^\[(\d+)\] \(saved [^)]*\) (.+)$", prompt, re.MULTILINE):
        key = m.group(2).strip().casefold()
        if key in first:
            picks.append({"id": int(m.group(1)), "kind": "duplicate", "keep_id": first[key], "reason": f"Same as {first[key]}."})
        else:
            first[key] = int(m.group(1))
    return {"archive": picks}


def _fake_digest(prompt: str) -> dict:
    """A fake news digest made from the real numbered article list (so the fact guard passes it)."""
    keys = re.findall(r"^- `(\w+)`:", prompt, re.MULTILINE)
    sections: dict[str, list[dict]] = {k: [] for k in keys}
    source = ""
    n = 0
    for line in prompt.splitlines():
        header = re.match(r"^### (.+) \(\d+\)$", line)
        if header:
            source = header.group(1)
            continue
        m = re.match(r"^\[(\d+)\] \d{4}-\d\d-\d\d · (.+)$", line)
        if not m or not keys:
            continue
        key = "trending" if "Trends" in source and "trending" in sections else keys[n % len(keys)]
        n += 1
        if len(sections[key]) < 3:
            sections[key].append({"article_ids": [int(m.group(1))], "headline": m.group(2), "summary": f"(fake digest) From {source}.", "importance": 10 - n % 9})
    return {"sections": [{"key": k, "items": v} for k, v in sections.items()]}


def fake_model_provider():
    model = FakeModel()
    return lambda _name: model
