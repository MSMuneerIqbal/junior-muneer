"""Opt-in one real-model code proposal on a throwaway source repo/database. Never tests or applies code."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/api/profile", timeout=5) as response:
        profile = json.load(response)
    with tempfile.TemporaryDirectory(prefix="junior-code-model-") as temp:
        data, root = Path(temp) / "data", Path(temp) / "repo"
        module = root / "backend/junior/demo.py"
        module.parent.mkdir(parents=True)
        module.write_text("def square(n):\n    return n + n\n", encoding="utf-8")
        (module.parent / "__init__.py").write_text("")
        def git(*args):
            subprocess.run(["git", "-c", "core.hooksPath=NUL", "-c", "commit.gpgsign=false", "-C", str(root), *args],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for args in [("init", "-q"), ("config", "user.name", "Synthetic check"), ("config", "user.email", "fixture@example.test"), ("add", "."), ("commit", "-qm", "fixture")]:
            git(*args)
        os.environ.update(DATA_DIR=str(data), SCHEDULER_ENABLED="false", JUNIOR_CODE_ROOT=str(root), LOG_LEVEL="WARNING")
        from junior.config import get_settings
        get_settings.cache_clear()
        from fastapi.testclient import TestClient
        from junior.main import create_app
        from junior.agent.context import TurnContext
        from junior.agent.helpers import HelperRunner
        from junior.agent.builder import openai_model_provider
        from junior.maintenance.code_tools import ask_code_for
        from junior.maintenance import code
        from junior.db import Conversation, Message, session_scope
        from junior.db.engine import close_all_connections
        from junior.settings_store import all_settings
        request = "Fix the square function in backend/junior/demo.py so square(3) returns 9. Propose only that small code fix; do not execute or apply it."
        try:
            with TestClient(create_app()) as client:
                client.put("/api/profile", json=profile).raise_for_status()
                with session_scope() as session:
                    conversation = Conversation(title="synthetic code check")
                    session.add(conversation)
                    session.flush()
                    message = Message(conversation_id=conversation.id, role="user", source="user", content=request)
                    session.add(message)
                    session.flush()
                    cid, mid = conversation.id, message.id
                context = TurnContext(conversation_id=cid, settings=all_settings(), user_text=request, user_message_ids=[mid])
                context.helpers = HelperRunner(client.app.state.registry, openai_model_provider())
                started = time.monotonic()
                result = asyncio.run(ask_code_for(context, request, request))
                proposals = code.list_proposals()
                assert len(proposals) == 1 and proposals[0]["status"] == "staged", result
                assert "n * n" in proposals[0]["diff"] or "n ** 2" in proposals[0]["diff"], "Unexpected proposed calculation"
                approvals = client.get("/api/approvals").json()
                assert len(approvals) == 1 and approvals[0]["status"] == "waiting"
                assert "return n + n" in module.read_text() and not (code.record_path(proposals[0]["id"]) / "checks.log").exists()
                print(json.dumps({"result": "passed", "seconds": round(time.monotonic()-started, 1), "estimated_cost_usd": sum(u.cost_usd for u in context.usage),
                                  "test_approval_waiting": True, "nothing_executed_or_applied": True}))
        finally:
            close_all_connections()
            get_settings.cache_clear()


if __name__ == "__main__":
    main()
