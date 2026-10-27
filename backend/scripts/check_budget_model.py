"""Opt-in one tiny real-model response through output/cost limits, on throwaway data/profile."""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with build_opener(ProxyHandler({})).open("http://127.0.0.1:8000/api/profile", timeout=5) as response:
        profile = json.load(response)
    with tempfile.TemporaryDirectory(prefix="junior-budget-check-") as temp:
        os.environ.update(DATA_DIR=temp, SCHEDULER_ENABLED="false", LOG_LEVEL="WARNING")
        from junior.config import get_settings
        get_settings.cache_clear()
        from fastapi.testclient import TestClient
        from junior.main import create_app
        from agents import Agent, ModelSettings
        from junior.agent.builder import openai_model_provider
        from junior.agent.context import TurnContext
        from junior.agent.runner import run_once
        from junior.db.engine import close_all_connections
        from junior.documents.limits import task_provider
        from junior.models import get_router
        from junior.settings_store import all_settings, set_setting
        try:
            with TestClient(create_app()) as client:
                client.put("/api/profile", json=profile).raise_for_status()
                set_setting("chat_budget_usd", .02)
                set_setting("chat_max_model_calls", 1)
                set_setting("max_output_tokens", 512)
                ctx = TurnContext(conversation_id=None, settings=all_settings())
                router = get_router()
                provider = task_provider(openai_model_provider(), ctx, router)
                name = router.tiers["small"]
                agent = Agent(name="budget_connection_check", instructions="Reply with exactly READY for this connection check.",
                              model=provider(name), model_settings=ModelSettings(max_tokens=512))
                started = time.monotonic()
                result = asyncio.run(run_once(agent, name, router, [{"role": "user", "content": "No conversation to summarize. For this connection check reply with exactly READY."}], ctx, .02))
                assert "READY" in result.text and len(ctx.usage) == 1
                assert ctx.usage[0].output_tokens <= 512 and result.cost_usd <= .02
                print(json.dumps({"result": "passed", "seconds": round(time.monotonic()-started, 1), "estimated_cost_usd": result.cost_usd,
                                  "model_calls": ctx.chat_model_calls, "output_tokens": ctx.usage[0].output_tokens, "output_limit": 512}))
        finally:
            close_all_connections()
            get_settings.cache_clear()


if __name__ == "__main__":
    main()
