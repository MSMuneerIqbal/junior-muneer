"""Ask Junior Muneer one question from the terminal (needs OPENAI_API_KEY in backend/.env).

    python -m junior.agent "What's the news in Pakistan today?"
"""

import asyncio
import sys

from junior.agent.builder import NoApiKeyError, build_agent, openai_model_provider
from junior.agent.context import TurnContext
from junior.agent.runner import stream_turn
from junior.db import init_db
from junior.models import get_router
from junior.registry import load_registry
from junior.settings_store import all_settings


async def main(question: str) -> None:
    init_db()
    router = get_router()
    agent, model = build_agent(load_registry().get("junior_muneer"), router, openai_model_provider())
    context = TurnContext(conversation_id=None, settings=all_settings())
    print(f"[{model}]")
    async for event in stream_turn(
        agent, model, router, [{"role": "user", "content": question}], context
    ):
        if event["type"] == "delta":
            print(event["text"], end="", flush=True)
        elif event["type"] == "step":
            print(f"\n  · {event['label']} ({event['status']})", flush=True)
        elif event["type"] == "final":
            print(f"\n\n[cost ${event['result'].cost_usd:.5f}]")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main(" ".join(sys.argv[1:]) or "Hi! Who are you?"))
    except NoApiKeyError as e:
        sys.exit(str(e))
