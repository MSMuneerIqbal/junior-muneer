"""Connect Google in the app: Google's own consent page, the login kept encrypted, and plain reasons when it fails."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from junior.config import get_settings
from junior.db import Connection, session_scope
from junior.google import auth
from junior.google.fake import FakeGoogle
from junior.main import create_app

import httpx


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    get_settings.cache_clear()
    fake = FakeGoogle()
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(fake))
    auth._access.clear()
    auth._flows.clear()
    with TestClient(create_app(), follow_redirects=False) as client:
        yield client, fake
    get_settings.cache_clear()


def sign_in(client) -> httpx.Response:
    start = client.get("/api/google/connect")
    assert start.status_code == 303
    query = parse_qs(urlsplit(start.headers["location"]).query)
    return client.get("/api/google/callback", params={"code": "code-1", "state": query["state"][0]})


def test_connect_opens_googles_consent_page_with_only_what_we_need(google):
    client, _ = google
    location = client.get("/api/google/connect").headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    q = parse_qs(urlsplit(location).query)
    assert q["client_id"] == ["client-123.apps.googleusercontent.com"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/google/callback"]
    assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    scopes = q["scope"][0].split()
    assert "https://www.googleapis.com/auth/drive.file" in scopes
    assert "https://www.googleapis.com/auth/drive.readonly" in scopes  # finding your files: read-only
    # Never anything that can change or delete your existing files, or read your Gmail.
    assert not any(s.endswith(("/drive", "gmail.readonly", "/documents", "/spreadsheets")) for s in scopes)


def test_signing_in_saves_the_login_encrypted(google):
    client, _ = google
    back = sign_in(client)
    assert back.status_code == 303
    assert back.headers["location"] == "http://localhost:3000/settings?google=connected&account=you%40example.com#connections"
    status = client.get("/api/google/status").json()
    assert status == {"configured": True, "connected": True, "account": "you@example.com", "missing": [],
                      "redirect_uri": "http://127.0.0.1:8000/api/google/callback"}
    with session_scope() as s:
        row = s.query(Connection).filter_by(provider="google").one()
        assert row.token_enc and "fake-refresh" not in row.token_enc  # encrypted
    assert asyncio.run(auth.access_token()) == "fake-access"


def test_a_used_or_made_up_state_is_refused(google):
    client, _ = google
    sign_in(client)
    back = client.get("/api/google/callback", params={"code": "code-2", "state": "made-up"})
    assert "google=error" in back.headers["location"] and "expired" in back.headers["location"]


def test_cancelling_on_google_connects_nothing(google):
    client, _ = google
    back = client.get("/api/google/callback", params={"error": "access_denied", "state": "x"})
    assert "cancelled" in back.headers["location"]
    assert client.get("/api/google/status").json()["connected"] is False


def test_permissions_you_unticked_are_named(google):
    client, fake = google
    fake.scopes = "openid email https://www.googleapis.com/auth/drive.file"
    sign_in(client)
    missing = client.get("/api/google/status").json()["missing"]
    assert missing == ["finding and sending you files from your Drive (read-only)", "reading your Google Docs",
                       "reading your Google Sheets", "reading and adding your calendar events"]
    assert not auth.has_scope("calendar.events") and auth.has_scope("drive.file")


def test_an_expired_login_says_connect_again(google):
    client, _ = google
    sign_in(client)
    auth._save("you@example.com", "revoked", fake_scopes())
    with pytest.raises(auth.GoogleError, match="Connect Google again"):
        asyncio.run(auth.access_token())


def fake_scopes() -> str:
    from junior.google.fake import SCOPES

    return SCOPES


def test_disconnect_forgets_it_and_asks_google_to_revoke(google):
    client, fake = google
    sign_in(client)
    assert client.delete("/api/google/connection").json()["disconnected"] is True
    assert fake.revoked == ["token=fake-refresh"]
    assert client.get("/api/google/status").json()["connected"] is False
    with pytest.raises(auth.GoogleError, match="isn't connected"):
        asyncio.run(auth.access_token())


def test_without_a_client_it_says_what_to_add(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), follow_redirects=False) as client:
            location = client.get("/api/google/connect").headers["location"]
            assert "google=error" in location and "GOOGLE_CLIENT_ID" in location
            assert client.get("/api/google/status").json()["configured"] is False
    finally:
        get_settings.cache_clear()


def test_google_answers_only_on_your_pc(google):
    client, _ = google
    r = client.get("/api/google/status", headers={"host": "abc.ngrok-free.dev"})
    assert r.status_code == 403
