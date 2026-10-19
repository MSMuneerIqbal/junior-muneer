"""Connect your Google account in the app (Google's own sign-in, OAuth), and call Google's APIs with it.

    GET    /api/google/connect      opens Google's consent page (from the Connect Google button)
    GET    /api/google/callback     Google sends you back here; the login is saved (encrypted)
    GET    /api/google/status       set up? connected? which account? anything you didn't allow?
    DELETE /api/google/connection   disconnect (also asks Google to revoke the app's access)

Only these permissions are asked for: files the app itself creates, finding and reading your Drive files
(read-only: never change, move or delete), reading your Docs and Sheets, your calendar's events, reading your
Gmail and making drafts (sent only after you approve each one), and your email address. The app's OAuth client comes from your
own Google Cloud project (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env). The refresh token
is encrypted in the database (junior/secrets.py) and never sent to the browser.
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from junior.audit import audit
from junior.config import get_settings
from junior.db import Connection, session_scope
from junior.db.models import utcnow
from junior.secrets import decrypt, encrypt

router = APIRouter()
PROVIDER = "google"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# What each scope is for, in plain words (shown when one wasn't allowed).
SCOPES = {
    "openid": "your sign-in",
    "email": "your email address",
    "https://www.googleapis.com/auth/drive.file": "creating Docs and Sheets in your Drive",
    "https://www.googleapis.com/auth/drive.readonly": "finding and sending you files from your Drive (read-only)",
    "https://www.googleapis.com/auth/documents.readonly": "reading your Google Docs",
    "https://www.googleapis.com/auth/spreadsheets.readonly": "reading your Google Sheets",
    "https://www.googleapis.com/auth/calendar.events": "reading and adding your calendar events",
    "https://www.googleapis.com/auth/gmail.readonly": "reading your Gmail",
    "https://www.googleapis.com/auth/gmail.compose": "making Gmail drafts and sending the ones you approve",
}
_ALIASES = {"https://www.googleapis.com/auth/userinfo.email": "email"}

TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests put a fake Google here
_flows: dict[str, dict] = {}  # sign-ins in progress: state -> {verifier, expires_at}
_access: dict[str, tuple[str, float]] = {}  # the current short-lived access token and when it expires
FLOW_SECONDS = 600


class GoogleError(RuntimeError):
    """Something went wrong with Google, in plain words."""


def configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def _fake() -> bool:
    s = get_settings()
    return s.fake_ai and s.google_client_id == "fake"


def transport() -> httpx.AsyncBaseTransport | None:
    if TRANSPORT is not None:
        return TRANSPORT
    if _fake():
        from junior.google.fake import fake_google

        return fake_google()
    return None


def client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, transport=transport(), **kwargs)


# ---- the saved login -------------------------------------------------------------------


def _row(s) -> Connection | None:
    return s.scalars(select(Connection).where(Connection.provider == PROVIDER)).first()


def stored() -> tuple[str, str, str]:
    """(account, refresh token, granted scopes), or empty strings if not connected."""
    with session_scope() as s:
        row = _row(s)
        return (row.account, decrypt(row.token_enc), row.scopes) if row else ("", "", "")


def is_connected() -> bool:
    return bool(stored()[1])


_PREFIX = "https://www.googleapis.com/auth/"


def _short(scopes: str) -> str:
    """Scopes as short names ('drive.file', 'email'), so they fit the database column."""
    return " ".join(sorted({_ALIASES.get(g, g).removeprefix(_PREFIX) for g in scopes.split()}))


def missing_scopes(granted: str) -> list[str]:
    have = set(_short(granted).split())
    return [what for scope, what in SCOPES.items() if scope.removeprefix(_PREFIX) not in have]


def has_scope(scope_end: str) -> bool:
    """Was this permission allowed (e.g. 'calendar.events')?"""
    return any(s.endswith(scope_end) for s in stored()[2].split())


def _save(account: str, refresh_token: str, scopes: str) -> None:
    with session_scope() as s:
        row = _row(s)
        if row is None:
            row = Connection(provider=PROVIDER, token_enc="")
            s.add(row)
        row.account, row.token_enc, row.scopes, row.updated_at = account, encrypt(refresh_token), _short(scopes), utcnow()
    _access.clear()
    audit("setting", "google_connected", detail={"account": account, "missing": missing_scopes(scopes)})


def forget() -> bool:
    with session_scope() as s:
        row = _row(s)
        if row is None:
            return False
        s.delete(row)
    _access.clear()
    audit("setting", "google_disconnected")
    return True


# ---- calling Google --------------------------------------------------------------------


async def access_token() -> str:
    """A fresh access token from the saved login (refreshed when it's about to run out)."""
    cached = _access.get("token")
    if cached and cached[1] > time.monotonic() + 60:
        return cached[0]
    _account, refresh, _scopes = stored()
    if not refresh:
        raise GoogleError("Google isn't connected. Connect it in Settings → Connections (Connect Google).")
    s = get_settings()
    data = {"client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token"}
    try:
        async with client() as c:
            r = await c.post(TOKEN_URL, data=data)
    except httpx.HTTPError:
        raise GoogleError("Couldn't reach Google. Check the internet connection and try again.") from None
    if r.status_code == 400 and r.json().get("error") == "invalid_grant":
        raise GoogleError("The Google login has expired or was removed. Connect Google again in Settings → Connections.")
    if r.status_code >= 400:
        raise GoogleError(f"Google refused the login ({r.status_code}).")
    got = r.json()
    _access["token"] = (got["access_token"], time.monotonic() + int(got.get("expires_in", 3600)))
    return got["access_token"]


async def call(method: str, url: str, **kwargs) -> dict:
    """One call to a Google API, as JSON. Raises GoogleError with a plain reason."""
    r = await _request(method, url, **kwargs)
    return r.json() if r.content else {}


async def download(url: str, **kwargs) -> bytes:
    """A file from a Google API (e.g. a doc exported as Word), as bytes."""
    return (await _request("GET", url, **kwargs)).content


async def _request(method: str, url: str, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {await access_token()}"}
    try:
        async with client(headers=headers) as c:
            r = await c.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise GoogleError("Couldn't reach Google. Check the internet connection and try again.") from None
    if r.status_code == 401:
        _access.clear()
        raise GoogleError("Google didn't accept the login. Connect Google again in Settings → Connections.")
    if r.status_code == 403:
        detail = _message(r)
        if "has not been used" in detail or "is disabled" in detail:
            raise GoogleError(f"That Google API isn't switched on in your Google Cloud project: {detail}")
        raise GoogleError(f"Google said you don't have access to that ({detail or 'forbidden'}).")
    if r.status_code == 404:
        raise GoogleError("Google couldn't find it. Check the link, and that it's shared with your account.")
    if r.status_code >= 400:
        raise GoogleError(f"Google said no ({r.status_code}: {_message(r)}).")
    return r


def _message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:300]
    except ValueError:
        return ""


# ---- signing in ------------------------------------------------------------------------


def consent_url() -> str:
    """Google's consent page for this app, with a one-time state and PKCE (the code can't be used by anyone else)."""
    if not configured():
        raise GoogleError(
            "Google isn't set up yet: add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env and restart."
        )
    now = time.monotonic()
    for state in [k for k, v in _flows.items() if v["expires_at"] < now]:
        _flows.pop(state)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    _flows[state] = {"verifier": verifier, "expires_at": now + FLOW_SECONDS}
    s = get_settings()
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # a refresh token, so you stay connected
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
        "code_challenge_method": "S256",
    }
    if _fake():  # a pretend Google approves at once
        return f"{s.google_redirect_uri}?{urlencode({'code': 'fake-code', 'state': state, 'scope': ' '.join(SCOPES)})}"
    return f"{AUTH_URL}?{urlencode(params)}"


async def finish(code: str, state: str) -> str:
    """Google sent you back: swap the code for the login, save it. Returns the account."""
    flow = _flows.pop(state, None)
    if flow is None or flow["expires_at"] < time.monotonic():
        raise GoogleError("That sign-in link expired or was already used. Start again with Connect Google.")
    s = get_settings()
    data = {"client_id": s.google_client_id, "client_secret": s.google_client_secret, "code": code,
            "code_verifier": flow["verifier"], "grant_type": "authorization_code", "redirect_uri": s.google_redirect_uri}
    try:
        async with client() as c:
            r = await c.post(TOKEN_URL, data=data)
            if r.status_code >= 400:
                raise GoogleError(f"Google didn't accept the sign-in ({r.status_code}: {r.json().get('error_description', '')}).")
            got = r.json()
            who = await c.get(USERINFO_URL, headers={"Authorization": f"Bearer {got['access_token']}"})
    except httpx.HTTPError:
        raise GoogleError("Couldn't reach Google. Check the internet connection and try again.") from None
    refresh = got.get("refresh_token", "")
    if not refresh:
        raise GoogleError("Google didn't give a lasting login. Disconnect the app at myaccount.google.com/permissions and connect again.")
    account = who.json().get("email", "") if who.status_code == 200 else ""
    _save(account, refresh, got.get("scope", ""))
    _access["token"] = (got["access_token"], time.monotonic() + int(got.get("expires_in", 3600)))
    return account


async def revoke() -> None:
    _account, refresh, _scopes = stored()
    if not refresh:
        return
    try:
        async with client() as c:
            await c.post(REVOKE_URL, data={"token": refresh})
    except httpx.HTTPError:
        pass  # forgotten here anyway; you can also remove it at myaccount.google.com/permissions


# ---- API --------------------------------------------------------------------------------


def _back(**params) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().frontend_origin}/settings?{urlencode(params)}#connections", status_code=303)


@router.get("/api/google/connect")
def connect() -> RedirectResponse:
    try:
        return RedirectResponse(consent_url(), status_code=303)
    except GoogleError as e:
        return _back(google="error", message=str(e))


@router.get("/api/google/callback")
async def callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if error:
        _flows.pop(state, None)
        return _back(google="error", message="You cancelled on Google. Nothing was connected." if error == "access_denied" else f"Google said: {error}")
    try:
        account = await finish(code, state)
    except GoogleError as e:
        return _back(google="error", message=str(e))
    return _back(google="connected", account=account)


@router.get("/api/google/status")
def status() -> dict:
    account, refresh, scopes = stored()
    return {
        "configured": configured(),
        "connected": bool(refresh),
        "account": account,
        "missing": missing_scopes(scopes) if refresh else [],
        "redirect_uri": get_settings().google_redirect_uri,
    }


@router.delete("/api/google/connection")
async def disconnect() -> dict:
    await revoke()
    if not forget():
        raise HTTPException(404, "Google wasn't connected.")
    return {"disconnected": True, "message": "Disconnected, and Google was asked to remove the app's access."}
