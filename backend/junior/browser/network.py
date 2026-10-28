"""A scoped forward proxy. Resolve once, validate every address, connect to the validated numeric IP.

Browser routes alone cannot prevent DNS rebinding. All Chromium TCP traffic goes through this authenticated
loopback proxy; QUIC, non-proxied WebRTC, service workers and websocket channels are disabled by the runtime.
No proxy credentials, cookies, response bodies or query strings are logged.
"""

import asyncio
import base64
import ipaddress
import re
import secrets
import socket
from urllib.parse import urlsplit, urlunsplit

MAX_CONNECTION_BYTES = 20 * 1024 * 1024
MAX_SESSION_BYTES = 100 * 1024 * 1024


class BrowserRefused(ValueError):
    pass


def public_address(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip.is_loopback or ip.is_link_local)


def origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if host.endswith(".") or not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise ValueError
        if any(ord(c) < 33 for c in url) or "\\" in url:
            raise ValueError
        return f"{parsed.scheme}://{host}"
    except (ValueError, UnicodeError):
        raise BrowserRefused("Use an HTTP(S) website with its standard port, no credentials or local address.") from None


def site(value: str) -> str:
    parsed = urlsplit(value.strip())
    result = origin(value.strip())
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BrowserRefused("Website scope must be an exact origin, for example https://example.com, without a path.")
    try:
        if not public_address(parsed.hostname):
            raise BrowserRefused("Local/private addresses cannot be allowed.")
    except ValueError as e:
        if isinstance(e, BrowserRefused):
            raise
    if parsed.hostname in {"localhost", "metadata.google.internal"} or parsed.hostname.endswith((".localhost", ".local", ".internal", ".home", ".lan")):
        raise BrowserRefused("Local/private hosts cannot be allowed.")
    return result


def checked_url(url: str, sites: list[str]) -> str:
    current = origin(url)
    # Even unrestricted scope excludes local/private hostnames and literal addresses.
    site(current)
    if "*" not in sites and current not in sites:
        raise BrowserRefused("That website is outside the exact origins allowed in Settings → Computer → Browser.")
    from junior.senders.guard import NEVER_SEND
    from urllib.parse import unquote
    decoded = unquote(url)
    if any(pattern.search(decoded) for pattern, _ in NEVER_SEND) or re.search(r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)=", decoded):
        raise BrowserRefused("Secrets must not be put in a browser URL.")
    return url


class ScopedProxy:
    def __init__(self, sites: list[str], active=lambda: True):
        self.sites = sites
        self.active = active
        self.token = secrets.token_urlsafe(32)
        self.auth = "Basic " + base64.b64encode(f"junior:{self.token}".encode()).decode()
        self.server = None
        self.tasks = set()
        self.bytes = 0
        self.connections = 0

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=32768)
        port = self.server.sockets[0].getsockname()[1]
        return {"server": f"http://127.0.0.1:{port}", "username": "junior", "password": self.token,
                "bypass": "<-loopback>"}

    async def resolve(self, host, port):
        rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in rows))
        if not addresses or any(not public_address(ip) for ip in addresses):
            raise BrowserRefused("Website DNS points at a private or reserved network.")
        return addresses[0]

    async def dial(self, ip, port):
        return await asyncio.open_connection(ip, port)

    async def _pipe(self, reader, writer, counter):
        while self.active():
            data = await asyncio.wait_for(reader.read(32768), 15)
            if not data:
                break
            counter[0] += len(data)
            self.bytes += len(data)
            if counter[0] > MAX_CONNECTION_BYTES or self.bytes > MAX_SESSION_BYTES:
                raise BrowserRefused("Browser transfer limit reached.")
            writer.write(data)
            await writer.drain()

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        upstream = None
        self.connections += 1
        try:
            if self.connections > 12 or not self.active():
                raise BrowserRefused("Browser network is unavailable.")
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 8)
            lines = header.decode("iso-8859-1").split("\r\n")
            method, target, version = lines[0].split(" ")
            fields = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            fields = {k.lower(): v.strip() for k, v in fields.items()}
            if fields.get("proxy-authorization") != self.auth:
                writer.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="Junior"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                await writer.drain()
                return
            connect = method == "CONNECT"
            url = f"https://{target}/" if connect else target
            checked_url(url, self.sites)
            parsed = urlsplit(url)
            port = 443 if connect else 80
            if connect and (parsed.port or 443) != 443 or not connect and parsed.scheme != "http":
                raise BrowserRefused("Unsupported proxy request.")
            ip = await asyncio.wait_for(self.resolve(parsed.hostname, port), 5)
            if not self.active():
                raise BrowserRefused("Browser stopped.")
            remote_reader, upstream = await asyncio.wait_for(self.dial(ip, port), 5)
            if connect:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                filtered = [line for line in lines[1:] if line and not line.lower().startswith(("proxy-", "connection:", "host:"))]
                body = f"{method} {path} {version}\r\nHost: {parsed.hostname}\r\n" + "\r\n".join(filtered) + "\r\nConnection: close\r\n\r\n"
                upstream.write(body.encode("iso-8859-1"))
                await upstream.drain()
            counter = [0]
            pending = [asyncio.create_task(self._pipe(reader, upstream, counter)),
                       asyncio.create_task(self._pipe(remote_reader, writer, counter))]
            try:
                await asyncio.wait(pending, timeout=45, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for pump in pending:
                    pump.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        except (ValueError, OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            try:
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
            except OSError:
                pass
        finally:
            self.connections -= 1
            streams = [writer, *([upstream] if upstream else [])]
            for stream in streams:
                stream.close()
            await asyncio.gather(*(asyncio.wait_for(stream.wait_closed(), 2) for stream in streams), return_exceptions=True)
            self.tasks.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
