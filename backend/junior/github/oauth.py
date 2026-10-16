"""Connect GitHub in the app, when it's needed (GitHub's device login, like the gh command).

    POST   /api/github/connect              start: {flow_id, user_code, verification_uri, interval, expires_in}
    POST   /api/github/connect/{flow_id}    check once: {status: pending|connected|expired|denied|error, account, message}
    DELETE /api/github/connection           disconnect (forget the token)

You open github.com/login/device, type the code and approve. The app gets your own token, which
is encrypted in the database and never sent to the browser. The app is registered once on GitHub
by its owner (GITHUB_CLIENT_ID in backend/.env: an OAuth App with device flow on; no secret needed).
"""

import secrets
import time

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from junior.audit import audit
from junior.config import get_settings
from junior.db import Connection, session_scope
from junior.db.models import utcnow
from junior.secrets import decrypt, encrypt

router = APIRouter()
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPES = "repo read:org"  # GitHub has no read-only scope for private repos: our code keeps it read-only
PROVIDER = "github"

# Logins in progress: flow id -> {device_code, interval, expires_at}. Short-lived, kept in memory.
_flows: dict[str, dict] = {}


class GitHubLoginError(RuntimeError):
    pass


def _client_id() -> str:
    client_id = get_settings().github_client_id
    if not client_id:
        raise GitHubLoginError(
            "This app isn't registered with GitHub yet: its owner adds GITHUB_CLIENT_ID to backend/.env (TASK.md, P6-01)."
        )
    return client_id


def _fake_github() -> httpx.MockTransport:
    """A pretend GitHub for trying the app (FAKE_AI with GITHUB_CLIENT_ID=fake): approves on the second check."""
    checks = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/device/code":
            return httpx.Response(200, json={"device_code": "fake", "user_code": "FAKE-1234",
                                             "verification_uri": "https://github.com/login/device", "interval": 1, "expires_in": 900})
        if request.url.path == "/login/oauth/access_token":
            checks["n"] += 1
            if checks["n"] % 2:
                return httpx.Response(200, json={"error": "authorization_pending"})
            return httpx.Response(200, json={"access_token": "gho_fake_for_trying_it", "scope": "repo"})
        return httpx.Response(200, json={"login": "fake-github-user"})

    return httpx.MockTransport(handler)


_FAKE = _fake_github()


def _default_transport(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncBaseTransport | None:
    s = get_settings()
    if transport is None and s.fake_ai and s.github_client_id == "fake":
        return _FAKE
    return transport


async def _post(url: str, data: dict, transport: httpx.AsyncBaseTransport | None) -> dict:
    transport = _default_transport(transport)
    async with httpx.AsyncClient(timeout=20, transport=transport, headers={"Accept": "application/json"}) as client:
        r = await client.post(url, data=data)
    if r.status_code >= 400:
        raise GitHubLoginError(f"GitHub said no ({r.status_code}).")
    return r.json()


async def start_login(transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Ask GitHub for a code you type at github.com/login/device."""
    try:
        got = await _post(DEVICE_CODE_URL, {"client_id": _client_id(), "scope": SCOPES}, transport)
    except httpx.HTTPError:
        raise GitHubLoginError("Couldn't reach GitHub. Check the internet connection and try again.") from None
    if "device_code" not in got:
        raise GitHubLoginError(got.get("error_description") or "GitHub didn't give a code. Is device flow on for the app?")
    flow_id = secrets.token_urlsafe(12)
    _flows[flow_id] = {
        "device_code": got["device_code"],
        "interval": int(got.get("interval", 5)),
        "expires_at": time.monotonic() + int(got.get("expires_in", 900)),
    }
    return {
        "flow_id": flow_id,
        "user_code": got["user_code"],
        "verification_uri": got.get("verification_uri", "https://github.com/login/device"),
        "interval": int(got.get("interval", 5)),
        "expires_in": int(got.get("expires_in", 900)),
    }


async def check_login(flow_id: str, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Has the person approved yet? On approval the token is saved (encrypted)."""
    flow = _flows.get(flow_id)
    if flow is None or time.monotonic() > flow["expires_at"]:
        _flows.pop(flow_id, None)
        return {"status": "expired", "account": "", "message": "The code expired. Start again."}
    data = {"client_id": _client_id(), "device_code": flow["device_code"], "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}
    try:
        got = await _post(TOKEN_URL, data, transport)
    except httpx.HTTPError:
        return {"status": "pending", "account": "", "message": "Couldn't reach GitHub; still trying."}
    error = got.get("error", "")
    if error in ("authorization_pending", "slow_down"):
        if error == "slow_down":
            flow["interval"] += 5
        return {"status": "pending", "account": "", "message": "Waiting for you to approve on GitHub.", "interval": flow["interval"]}
    _flows.pop(flow_id, None)
    if error == "access_denied":
        return {"status": "denied", "account": "", "message": "You cancelled on GitHub. Nothing was connected."}
    if error == "expired_token":
        return {"status": "expired", "account": "", "message": "The code expired. Start again."}
    token = got.get("access_token", "")
    if not token:
        return {"status": "error", "account": "", "message": got.get("error_description") or "GitHub didn't send a token."}
    account = await _login_of(token, transport)
    save_connection(account, token, got.get("scope", ""))
    return {"status": "connected", "account": account, "message": f"Connected as @{account}."}


async def _login_of(token: str, transport: httpx.AsyncBaseTransport | None) -> str:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    transport = _default_transport(transport)
    try:
        async with httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=15, transport=transport) as client:
            r = await client.get("/user")
        return r.json().get("login", "") if r.status_code == 200 else ""
    except httpx.HTTPError:
        return ""


def save_connection(account: str, token: str, scopes: str = "") -> None:
    with session_scope() as s:
        row = s.scalars(select(Connection).where(Connection.provider == PROVIDER)).first()
        if row is None:
            row = Connection(provider=PROVIDER, token_enc="")
            s.add(row)
        row.account, row.token_enc, row.scopes, row.updated_at = account, encrypt(token), scopes, utcnow()
    audit("setting", "github_connected", detail={"account": account, "scopes": scopes})


def stored_token() -> str:
    """The token you connected in the app ('' if none)."""
    with session_scope() as s:
        row = s.scalars(select(Connection).where(Connection.provider == PROVIDER)).first()
        return decrypt(row.token_enc) if row else ""


def stored_account() -> str:
    with session_scope() as s:
        row = s.scalars(select(Connection).where(Connection.provider == PROVIDER)).first()
        return row.account if row else ""


def forget_connection() -> bool:
    with session_scope() as s:
        row = s.scalars(select(Connection).where(Connection.provider == PROVIDER)).first()
        if row is None:
            return False
        s.delete(row)
    audit("setting", "github_disconnected")
    return True


# ---- API --------------------------------------------------------------------


@router.post("/api/github/connect")
async def connect_start() -> dict:
    try:
        return await start_login()
    except GitHubLoginError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/api/github/connect/{flow_id}")
async def connect_check(flow_id: str) -> dict:
    try:
        return await check_login(flow_id)
    except GitHubLoginError as e:
        raise HTTPException(409, str(e)) from None


@router.delete("/api/github/connection")
def disconnect() -> dict:
    forgot = forget_connection()
    return {
        "disconnected": forgot,
        "message": "Disconnected. To remove the app's access on GitHub too: github.com → Settings → Applications."
        if forgot
        else "GitHub wasn't connected in the app.",
    }
