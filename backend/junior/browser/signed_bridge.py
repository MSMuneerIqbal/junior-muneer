"""Local, explicitly paired transport for the owner's browser extension.

This transport does not grant actions. Callers must validate requests through the
normal browser/media permission and target checks before sending a command.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from junior.db import Setting, session_scope

EXTENSION_ID = "boaiofelelhnkakifhjimmcahfeeifen"
EXTENSION_ORIGIN = "chrome-extension://" + EXTENSION_ID
PAIRING_KEY = "_signed_browser_pairing_hash"
MAX_MESSAGE_BYTES = 128_000


def local_peer(host: str | None) -> bool:
    try:
        return bool(host and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        return False


def issue_pairing_code() -> str:
    """Return a new secret once; persist only its hash in the private database."""
    secret = secrets.token_urlsafe(32)
    digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
    with session_scope() as session:
        setting = session.get(Setting, PAIRING_KEY)
        if setting is None:
            session.add(Setting(key=PAIRING_KEY, value=digest))
        else:
            setting.value = digest
    return secret


def paired(secret: object) -> bool:
    if not isinstance(secret, str) or not 32 <= len(secret) <= 100 or not secret.isascii():
        return False
    digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
    with session_scope() as session:
        existing = session.scalar(select(Setting.value).where(Setting.key == PAIRING_KEY))
    return isinstance(existing, str) and hmac.compare_digest(existing, digest)


def revoke_pairing() -> None:
    with session_scope() as session:
        setting = session.get(Setting, PAIRING_KEY)
        if setting is not None:
            session.delete(setting)


class SignedBrowserBridge:
    def __init__(self):
        self.socket: WebSocket | None = None
        self.generation = uuid4().hex
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.socket is not None

    async def disconnect(self):
        async with self.lock:
            socket, self.socket = self.socket, None
            self.generation = uuid4().hex
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("The signed-in browser disconnected."))
            self.pending.clear()
            if socket:
                try:
                    await socket.close(code=1000)
                except (RuntimeError, OSError):
                    pass

    async def command(self, name: str, payload: dict, timeout: float = 30):
        """One bounded request; a disconnect or timeout is an uncertain result."""
        if name not in {"navigate", "snapshot", "click", "fill", "media_play", "media_next", "media_stop", "media_status"}:
            raise ValueError("Unsupported signed-in browser operation.")
        async with self.lock:
            if self.socket is None:
                raise ConnectionError("Connect the signed-in browser extension in Settings → Computer.")
            if len(self.pending) >= 8:
                raise ConnectionError("The signed-in browser is busy.")
            ident = uuid4().hex
            future = asyncio.get_running_loop().create_future()
            self.pending[ident] = future
            try:
                await self.socket.send_json({"id": ident, "command": name, "payload": payload})
            except BaseException:
                self.pending.pop(ident, None)
                raise
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(ident, None)

    async def serve(self, socket: WebSocket):
        """Accept only the pinned extension from this machine, then authenticate it."""
        if not local_peer(socket.client.host if socket.client else None) or socket.headers.get("origin") != EXTENSION_ORIGIN:
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            raw = await asyncio.wait_for(socket.receive_text(), 5)
            if len(raw) > 500:
                await socket.close(code=1008)
                return
            import json
            hello = json.loads(raw)
            if not isinstance(hello, dict) or set(hello) != {"token"} or not paired(hello["token"]):
                await socket.close(code=1008)
                return
            await self.disconnect()
            async with self.lock:
                self.socket = socket
                self.generation = uuid4().hex
            await socket.send_json({"connected": True})
            while True:
                raw = await socket.receive_text()
                if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    break
                message = json.loads(raw)
                if message == {"ping": True}:
                    await socket.send_json({"pong": True})
                    continue
                if message == {"unpair": True}:
                    revoke_pairing()
                    break
                if not isinstance(message, dict) or set(message) != {"id", "result"}:
                    break
                future = self.pending.get(message["id"]) if isinstance(message["id"], str) else None
                if future is not None and not future.done():
                    future.set_result(message["result"])
        except (WebSocketDisconnect, TimeoutError, ValueError, TypeError, RuntimeError):
            pass
        finally:
            if self.socket is socket:
                await self.disconnect()
