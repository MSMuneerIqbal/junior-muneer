from fastapi.testclient import TestClient

from junior.main import create_app


def test_health_answers_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_data_dir_comes_from_settings(isolated_settings, tmp_path):
    assert isolated_settings.db_path == tmp_path / "data" / "junior.db"


def test_closed_connection_noise_is_filtered():
    import logging

    from junior.logging_setup import setup_logging

    setup_logging()
    logger = logging.getLogger("asyncio")
    noise = logger.makeRecord("asyncio", logging.ERROR, __file__, 1, "x", (), (ConnectionResetError, ConnectionResetError(), None))
    real = logger.makeRecord("asyncio", logging.ERROR, __file__, 1, "x", (), (ValueError, ValueError(), None))
    assert not logger.filter(noise)
    assert logger.filter(real)


def test_untrusted_website_cannot_post_local_actions():
    with TestClient(create_app()) as c:
        for headers in ({"Origin": "https://outside.example"}, {"Origin": "null"},
                        {"Sec-Fetch-Site": "cross-site"}):
            result = c.post("/api/computer/browser/connect", headers=headers, json={"port": 9222})
            assert result.status_code == 403
        # The real dashboard can be cross-site relative to 127.0.0.1; configured Origin is what grants access.
        assert c.post("/api/computer/browser/connect", headers={"Origin": "http://localhost:3000", "Sec-Fetch-Site": "cross-site"}, json={"port": 9222}).status_code == 409
        # Cross-site safe navigations (OAuth callbacks) are allowed through to their own state checks.
        assert c.get("/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_untrusted_website_cannot_open_local_chat_websocket():
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with TestClient(create_app()) as c:
        with pytest.raises(WebSocketDisconnect) as error:
            with c.websocket_connect("/ws/chat", headers={"Origin": "https://outside.example"}):
                pass
        assert error.value.code == 1008
