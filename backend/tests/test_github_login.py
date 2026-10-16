"""Connect GitHub in the app (device login): the token is your own, encrypted, never sent to the browser."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from junior.config import get_settings
from junior.db import Connection, session_scope
from junior.github import connection, oauth
from junior.main import create_app

TOKEN = "gho_" + "Z9y8X7w6V5u4" * 3  # not a real token


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "Iv1.testclientid")
    get_settings.cache_clear()


def github(answers: list):
    """Fake GitHub: the device code, then each token check in turn, and /user."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/login/device/code":
            return httpx.Response(200, json={"device_code": "dev123", "user_code": "WDJB-MJHT",
                                             "verification_uri": "https://github.com/login/device", "interval": 5, "expires_in": 900})
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json=answers.pop(0))
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "MSMuneerIqbal"})
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


def test_connect_github_in_the_app(registered):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))):
        transport, seen = github([{"error": "authorization_pending"}, {"error": "slow_down"},
                                  {"access_token": TOKEN, "scope": "repo,read:org"}])
        started = asyncio.run(oauth.start_login(transport))
        assert started["user_code"] == "WDJB-MJHT" and started["verification_uri"] == "https://github.com/login/device"
        assert "device_code" not in started  # stays on the server
        assert b"client_id=Iv1.testclientid" in seen[0].content and b"scope=repo+read%3Aorg" in seen[0].content

        flow = started["flow_id"]
        assert asyncio.run(oauth.check_login(flow, transport))["status"] == "pending"
        slow = asyncio.run(oauth.check_login(flow, transport))
        assert slow["status"] == "pending" and slow["interval"] == 10  # GitHub asked to slow down
        done = asyncio.run(oauth.check_login(flow, transport))
        assert done == {"status": "connected", "account": "MSMuneerIqbal", "message": "Connected as @MSMuneerIqbal."}

        with session_scope() as s:
            row = s.scalars(select(Connection)).one()
            assert row.account == "MSMuneerIqbal" and TOKEN not in row.token_enc  # encrypted at rest
        assert oauth.stored_token() == TOKEN and connection.saved_token() == TOKEN and connection.source() == "app"
        assert asyncio.run(oauth.check_login(flow, transport))["status"] == "expired"  # a flow is used once


@pytest.mark.parametrize(("answer", "status"), [({"error": "access_denied"}, "denied"), ({"error": "expired_token"}, "expired")])
def test_cancelled_or_expired_connects_nothing(registered, answer, status):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))):
        transport, _ = github([answer])
        flow = asyncio.run(oauth.start_login(transport))["flow_id"]
        assert asyncio.run(oauth.check_login(flow, transport))["status"] == status
        assert oauth.stored_token() == "" and connection.source() == ""


def test_not_registered_with_github_yet():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        r = c.post("/api/github/connect")
        assert r.status_code == 409 and "GITHUB_CLIENT_ID" in r.json()["detail"]
        row = next(p for p in c.get("/api/connections").json() if p["key"] == "github")
        assert row["connect"] == "" and row["connected"] is False


def test_the_browser_never_gets_the_token_and_you_can_disconnect(registered):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        oauth.save_connection("MSMuneerIqbal", TOKEN, "repo")
        row = next(p for p in c.get("/api/connections").json() if p["key"] == "github")
        assert row["connected"] is True and row["source"] == "app" and row["account"] == "MSMuneerIqbal"
        assert row["connect"] == "device" and TOKEN not in c.get("/api/connections").text

        r = c.delete("/api/github/connection").json()
        assert r["disconnected"] is True and "github.com → Settings → Applications" in r["message"]
        assert oauth.stored_token() == "" and c.delete("/api/github/connection").json()["disconnected"] is False


def test_a_token_from_another_key_is_not_used(registered, tmp_path):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))):
        oauth.save_connection("MSMuneerIqbal", TOKEN)
        (get_settings().data_path / "secret.key").write_bytes(b"x" * 43 + b"=")  # a different key
        assert oauth.stored_token() == ""
