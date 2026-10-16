"""A request the AI service never answers gives up in time, and the chat says so."""

import socket
import threading
import time

from fastapi.testclient import TestClient

from junior.agent.builder import openai_model_provider
from junior.calls import OpenAIRealtime
from junior.config import get_settings
from junior.main import create_app
from junior.voice import OpenAIVoice


def silent_server():
    """Accepts connections but never answers, like a hung API."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held: list[socket.socket] = []

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            held.append(conn)

    threading.Thread(target=serve, daemon=True).start()
    return server, held


def test_a_hung_ai_request_gives_up_and_says_so(monkeypatch):
    server, held = silent_server()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.getsockname()[1]}/v1")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "0.5")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(model_provider=openai_model_provider)) as c:
            started = time.monotonic()
            with c.websocket_connect("/ws/chat") as ws:
                ws.send_json({"type": "message", "conversation_id": None, "text": "Hello"})
                while (e := ws.receive_json())["type"] not in ("done", "error"):
                    pass
            assert e["type"] == "error"
            assert e["message"] == (
                "The AI service didn't answer within 0.5 seconds, so I stopped waiting. Please send it again."
            )
            assert time.monotonic() - started < 15  # not 10 minutes
            assert len(held) == 2  # tried once more, then gave up
            run = c.get("/api/activity?kind=agent_run").json()[0]
            assert run["result"] == "error" and "didn't answer" in run["detail"]["error"]
    finally:
        server.close()
        for conn in held:
            conn.close()


def test_every_ai_client_has_the_time_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    get_settings.cache_clear()
    for client in (OpenAIVoice().client, OpenAIRealtime().client):
        assert client.timeout.read == 120
        assert client.timeout.connect == 15
        assert client.max_retries == 1
