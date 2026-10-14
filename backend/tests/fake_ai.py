"""Fake AI for tests: scripted model answers, no network, no cost."""

import copy

from agents import Usage
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from agents.testing.model import _stream_events_for_step
from openai.types.responses import (
    ResponseFunctionWebSearch,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_function_web_search import ActionSearch
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from junior.models import parse_router

TEST_ROUTER = parse_router(
    """
[tiers]
strong = "fake-strong"
small = "fake-small"

[prices."fake-strong"]
input = 2.0
cached_input = 0.1
output = 10.0

[prices."fake-small"]
input = 0.1
output = 0.5

[tool_prices]
web_search = 0.01
"""
)

__all__ = ["ScriptedModel", "TEST_ROUTER", "assistant_message", "function_call", "usage"]


def usage(input_tokens: int = 1000, output_tokens: int = 100, cached: int = 0) -> Usage:
    return Usage(
        requests=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=cached, cache_write_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )


def chunked_answer(text: str, size: int = 4, u: Usage | None = None) -> ModelStep:
    """An answer that streams in pieces of `size` characters, like the real API."""
    step = ModelStep(output=[assistant_message(text)], usage=u or usage())
    events = []
    for event in _stream_events_for_step(step, preserve_raw_usage=False):
        if isinstance(event, ResponseTextDeltaEvent):
            for i in range(0, len(event.delta), size):
                piece = copy.copy(event)
                piece.delta = event.delta[i : i + size]
                events.append(piece)
        else:
            events.append(event)
    return ModelStep.stream(events, output=step.output, usage=step.usage)


def with_web_search(query: str, output: list, u: Usage | None = None) -> ModelStep:
    """A response where the model searched the web, then produced `output`
    (an answer and/or tool calls)."""
    search = ResponseFunctionWebSearch(
        id="ws_1",
        status="completed",
        type="web_search_call",
        action=ActionSearch(type="search", query=query),
    )
    step = ModelStep(output=output, usage=u or usage())
    events = _stream_events_for_step(step, preserve_raw_usage=False)
    running = search.model_copy(update={"status": "in_progress"})
    web = [
        ResponseOutputItemAddedEvent(
            type="response.output_item.added", item=running, output_index=0, sequence_number=0
        ),
        ResponseOutputItemDoneEvent(
            type="response.output_item.done", item=search, output_index=0, sequence_number=0
        ),
    ]
    completed = events[-1]
    completed.response.output = [search, *completed.response.output]
    events = events[:2] + web + events[2:]
    return ModelStep.stream(events, output=[search, *step.output], usage=step.usage)


def answer_after_web_search(query: str, text: str, u: Usage | None = None) -> ModelStep:
    return with_web_search(query, [assistant_message(text)], u)
