"""Who may use the backend (P8-04): your PC, your server's own domain, and - from anywhere - only
the WhatsApp webhook.

A tunnel (to test WhatsApp on your PC) gives the backend a public address. Without this check,
anyone who found that address could read your chats and spend your API key. Requests that come
in under any other address get 403, except Meta's webhook calls (checked by their signature).
Covers web requests and the chat's WebSocket.
"""

from junior.config import get_settings

LOCAL = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}
OPEN_TO_ALL = {"/api/whatsapp/webhook"}


def _host(scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"host":
            host = value.decode("latin-1").strip().lower()
            if host.startswith("["):  # [::1]:8000
                return host.split("]")[0] + "]"
            return host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return ""


def allowed(scope) -> bool:
    if scope.get("path") in OPEN_TO_ALL:
        return True
    host = _host(scope)
    public = {h.strip().lower() for h in get_settings().public_hosts.split(",") if h.strip()}
    return host in LOCAL or host in public


def trusted_origin(scope) -> bool:
    """CORS limits reading responses, but cannot by itself prevent cross-site POST/WebSocket actions."""
    if scope.get("path") in OPEN_TO_ALL:
        return True  # the webhook keeps its existing signature/authentication boundary
    headers = {k.lower(): v.decode("latin-1").strip() for k, v in scope.get("headers", [])}
    origin = headers.get(b"origin")
    if not origin:
        unsafe = scope["type"] == "websocket" or scope.get("method", "GET") not in {"GET", "HEAD", "OPTIONS"}
        return not (unsafe and headers.get(b"sec-fetch-site") == "cross-site")
    frontend = get_settings().frontend_origin.rstrip("/")
    scheme = {"ws": "http", "wss": "https"}.get(scope.get("scheme"), scope.get("scheme", "http"))
    same_backend = f"{scheme}://{headers.get(b'host', '')}"
    return origin in {frontend, frontend.replace("localhost", "127.0.0.1"),
                      frontend.replace("127.0.0.1", "localhost"), same_backend}


class LocalOnly:
    """ASGI middleware: everything but the webhook answers only to your PC and your own domain."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and not (allowed(scope) and trusted_origin(scope)):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Not available from outside."}'})
            return
        await self.app(scope, receive, send)
