"""P6-01: your GitHub token and GitHub's MCP server, read-only (two locks), never in tests or the browser."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import connect
from junior.config import get_settings
from junior.github.connection import MCP_READONLY_URL, _only_reads, check_token, github_mcp
from junior.main import create_app

TOKEN = "github_pat_" + "A1b2C3d4E5f6G7h8I9j0" * 3  # not a real token


def test_tests_never_see_your_real_token():
    assert get_settings().github_token == ""


def test_the_mcp_server_is_read_only_with_your_token():
    server = github_mcp(TOKEN)
    assert server.params["url"] == MCP_READONLY_URL and MCP_READONLY_URL.endswith("/readonly")
    headers = server.params["headers"]
    assert headers["Authorization"] == f"Bearer {TOKEN}" and headers["X-MCP-Readonly"] == "true"
    assert set(headers["X-MCP-Toolsets"].split(",")) == {"context", "repos", "issues", "pull_requests"}
    with pytest.raises(ValueError, match="connect.bat github"):
        github_mcp("")


@pytest.mark.parametrize(
    ("name", "allowed"),
    [
        ("get_me", True),
        ("list_commits", True),
        ("search_issues", True),
        ("get_pull_request_diff", True),
        ("create_issue", False),
        ("update_issue", False),
        ("merge_pull_request", False),
        ("push_files", False),
        ("delete_file", False),
        ("create_or_update_file", False),
        ("add_issue_comment", False),
    ],
)
def test_code_lets_through_only_tools_that_read(name, allowed):
    """The second lock: even if GitHub offered a write tool, the agent never sees it."""
    assert _only_reads(None, SimpleNamespace(name=name)) is allowed


def github(handler):
    return httpx.MockTransport(handler)


def test_checking_the_token():
    seen = {}

    def ok(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"login": "MSMuneerIqbal"}, headers={"github-authentication-token-expiration": "2027-01-15 10:00:00 UTC"})

    result = asyncio.run(check_token(TOKEN, github(ok)))
    assert result == "Connected as @MSMuneerIqbal; the token expires 2027-01-15 10:00:00 UTC."
    assert seen["auth"] == f"Bearer {TOKEN}"

    assert "doesn't work" in asyncio.run(check_token(TOKEN, github(lambda r: httpx.Response(401))))

    def down(request):
        raise httpx.ConnectError("no internet")

    assert asyncio.run(check_token(TOKEN, github(down))).startswith("Couldn't reach GitHub")
    assert asyncio.run(check_token("")) == "Not connected. Run connect.bat github."


def test_github_shows_in_connections(monkeypatch):
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        row = next(p for p in c.get("/api/connections").json() if p["key"] == "github")
        assert row["connected"] is False and row["how"] == "connect.bat github"

    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    get_settings.cache_clear()

    async def fake_check(token):
        return f"Connected as @MSMuneerIqbal (token ends {token[-4:]})."

    monkeypatch.setattr("junior.github.connection.check_token", fake_check)
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        row = next(p for p in c.get("/api/connections").json() if p["key"] == "github")
        assert row["connected"] is True and TOKEN not in str(row)  # the token never goes to the browser
        result = c.post("/api/connections/github/check").json()["result"]
        assert result.startswith("Connected as @MSMuneerIqbal") and TOKEN not in result


def test_connect_github_saves_only_a_working_token(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-keep\n", encoding="utf-8")
    monkeypatch.setattr(connect, "ENV_FILE", env)

    monkeypatch.setattr(connect.getpass, "getpass", lambda prompt="": "not-a-token")
    with pytest.raises(SystemExit, match="doesn't look like a GitHub token"):
        connect.connect_github()

    monkeypatch.setattr(connect.getpass, "getpass", lambda prompt="": TOKEN)

    async def revoked(token):
        return "The token doesn't work (expired or revoked)."

    monkeypatch.setattr(connect, "check_token", revoked)
    with pytest.raises(SystemExit, match="Nothing was saved"):
        connect.connect_github()
    assert "GITHUB_TOKEN" not in env.read_text(encoding="utf-8")

    async def works(token):
        return "Connected as @MSMuneerIqbal."

    monkeypatch.setattr(connect, "check_token", works)
    connect.connect_github()
    text = env.read_text(encoding="utf-8")
    assert f"GITHUB_TOKEN={TOKEN}" in text and "OPENAI_API_KEY=sk-keep" in text
    assert "# GitHub (written by connect.bat github)" in text
