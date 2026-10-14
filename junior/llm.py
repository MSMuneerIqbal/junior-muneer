"""One place that talks to Claude. Every agent calls ask() and gets back a checked Pydantic object."""

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from . import db
from .config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# If Claude's safety checks wrongly decline a request, the API retries it on a suitable
# fallback model instead of failing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """A problem worth showing to the owner as-is."""


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment / .env
    return _client


def ask(agent: str, system: str, prompt: str, output: type[T]) -> T:
    try:
        response = client().beta.messages.parse(
            model=settings.model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output,
            output_config={"effort": settings.effort},
        )
    except anthropic.AuthenticationError as e:
        raise LLMError("Your Claude API key is missing or wrong. Check ANTHROPIC_API_KEY in the .env file.") from e
    except anthropic.PermissionDeniedError as e:
        raise LLMError(f"Your API key can't use this model ({settings.model}).") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Model not found: {settings.model}. Check CLAUDE_MODEL in the .env file.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Claude API limit reached. Wait a minute, then click Try again.") from e
    except anthropic.APIStatusError as e:
        if e.status_code == 400 and "credit" in str(e.message).lower():
            raise LLMError("Your Claude API account is out of credit. Add credit, then try again.") from e
        raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the Claude API. Check your internet connection.") from e

    db.log_usage(response.model, agent, response.usage.input_tokens, response.usage.output_tokens)

    if response.stop_reason == "refusal":
        raise LLMError("Claude declined to write this. Try rewording the topic.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        log.warning("Unreadable answer from %s (stop_reason=%s)", agent, response.stop_reason)
        raise LLMError("Claude's answer came back incomplete. Click Try again.")
    return response.parsed_output
