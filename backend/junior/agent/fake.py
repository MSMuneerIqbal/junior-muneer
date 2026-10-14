"""Fake AI for trying the dashboard without an API key (FAKE_AI=true). No network, no cost.

It echoes your message, streamed in small pieces. Two tricks to see the UI work:
  - a message containing "search" shows a (pretend) web search step;
  - a message starting with "remember " saves the rest as a memory, through the
    real save_memory tool and its safety checks.
"""

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from typing import Any

from agents import Model, ModelResponse, Usage
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


def _last_user_text(items: Any) -> str:
    if isinstance(items, str):
        return items
    for item in reversed(items):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            return content if isinstance(content, str) else json.dumps(content)
    return ""


class FakeModel(Model):
    def _plan(self, input: Any) -> tuple[list[Any], bool]:
        """What to answer: (output items, include a web search)."""
        last = input[-1] if isinstance(input, list) and input else None
        if isinstance(last, dict) and last.get("type") == "function_call_output":
            return [assistant_message(f"(fake AI) Tool said: {last.get('output')}")], False
        text = _last_user_text(input)
        if text.lower().startswith("remember "):
            words = text[len("remember ") :].strip()
            return [
                function_call(
                    "save_memory", {"fact": words, "your_words": words}, call_id="fake-mem"
                )
            ], False
        reply = (
            "(fake AI) You said:\n\n"
            f"> {text}\n\n"
            "Add your OpenAI key to `backend/.env` and turn `FAKE_AI` off for real answers."
        )
        return [assistant_message(reply)], "search" in text.lower()

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs) -> ModelResponse:  # noqa: E501
        output, _ = self._plan(input)
        return ModelResponse(output=output, usage=_usage(str(input), str(output)), response_id="fake")

    async def stream_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs) -> AsyncIterator[Any]:  # noqa: E501
        output, with_search = self._plan(input)
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


def fake_model_provider():
    model = FakeModel()
    return lambda _name: model
