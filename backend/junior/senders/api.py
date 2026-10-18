"""Sending API (P3-01).

    POST /api/approvals/{id}/send               send an approved API item now (Safety Guard first)
    POST /api/approvals/{id}/resolve  {"posted"}  after "check manually": did it really go out?
    GET  /api/connections                        which platforms can post through their API
    POST /api/connections/{key}/check            does the saved token still work?
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from junior.approvals import ApprovalError, ApprovalOut
from junior.senders.dispatch import SendError, resolve_unclear, send_item

router = APIRouter()


class ResolveBody(BaseModel):
    posted: bool


@router.post("/api/approvals/{item_id}/send", response_model=ApprovalOut)
async def post_send(item_id: int, request: Request) -> ApprovalOut:
    try:
        return await send_item(item_id, request.app.state.senders)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except SendError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/api/approvals/{item_id}/resolve", response_model=ApprovalOut)
def post_resolve(item_id: int, body: ResolveBody) -> ApprovalOut:
    try:
        return resolve_unclear(item_id, body.posted)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ApprovalError as e:
        raise HTTPException(409, str(e)) from None


def _github() -> dict:
    from junior.config import get_settings
    from junior.github.connection import source
    from junior.github.oauth import stored_account

    where = source()
    return {"key": "github", "label": "GitHub (read-only for now)", "action": "", "how": "connect.bat github", "ready": True,
            "connected": bool(where), "sender": "GitHub MCP" if where else "",
            # Connect GitHub in the app (device login), when the app is registered with GitHub.
            "connect": "device" if get_settings().github_client_id else "", "source": where, "account": stored_account()}


def _whatsapp() -> dict:
    from junior.whatsapp import configured

    on = configured()
    return {"key": "whatsapp", "label": "WhatsApp (chat with Junior)", "action": "", "how": "connect.bat whatsapp", "ready": True,
            "connected": on, "sender": "WhatsApp Cloud API" if on else ""}


@router.get("/api/connections")
def connections(request: Request) -> list[dict]:
    return [*request.app.state.senders.platforms(), _github(), _whatsapp()]


@router.post("/api/connections/{key}/check")
async def check_connection(key: str, request: Request) -> dict:
    if key == "whatsapp":
        from junior.whatsapp import client, configured

        return {"key": key, "result": await client().check() if configured() else "Not connected. Run connect.bat whatsapp."}
    if key == "github":
        import asyncio

        from junior.github import connection

        token = await asyncio.to_thread(connection.saved_token)
        return {"key": key, "result": await connection.check_token(token)}
    return {"key": key, "result": await request.app.state.senders.check(key)}
