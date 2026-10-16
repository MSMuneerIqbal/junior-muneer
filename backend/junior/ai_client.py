"""The OpenAI client every AI call uses, with a time limit.

Without one, a request the server never answers waits 10 minutes, then is tried
twice more, and the chat looks frozen. With it, a silent request gives up after
AI_TIMEOUT_SECONDS (backend/.env, default 2 minutes), is tried once more, and
the chat says what happened.
"""

import httpx
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from junior.config import get_settings

CONNECT_SECONDS = 15.0
RETRIES = 1


def ai_client(api_key: str, base_url: str | None = None) -> AsyncOpenAI:
    seconds = get_settings().ai_timeout_seconds
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(seconds, connect=min(CONNECT_SECONDS, seconds)),
        max_retries=RETRIES,
    )


def no_answer_message(e: APIConnectionError) -> str:
    """Plain words for a request that timed out or couldn't connect."""
    if isinstance(e, APITimeoutError):
        seconds = get_settings().ai_timeout_seconds
        wait = f"{seconds / 60:g} minutes" if seconds >= 120 and seconds % 60 == 0 else f"{seconds:g} seconds"
        return f"The AI service didn't answer within {wait}, so I stopped waiting. Please send it again."
    return "Couldn't reach the AI service. Check the internet connection, then send it again."
