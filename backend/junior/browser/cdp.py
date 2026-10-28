"""Validate an owner-selected loopback debugging endpoint and compatible network policy before attachment."""

import json
import re
from urllib.parse import urlsplit

import httpx

from junior.browser.network import BrowserRefused

NETWORK_ARGS = ["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--disable-features=WebTransport,WebUSB,WebBluetooth,Serial,DirectSockets",
                "--disable-background-networking", "--disable-extensions"]


def validate_peer(body: dict, port: int) -> str:
    value = body.get("webSocketDebuggerUrl", "")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port != port
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not re.fullmatch(r"/devtools/browser/[a-fA-F0-9-]{16,64}", parsed.path)
                or not re.match(r"^(?:HeadlessChrome|Chrome|Chromium|Edg|Microsoft Edge)/", body.get("Browser", ""))):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise BrowserRefused("That port did not return a valid same-port loopback Chromium browser endpoint.") from None
    return value


async def endpoint(port: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
            async with client.stream("GET", f"http://127.0.0.1:{port}/json/version") as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 8192:
                        raise ValueError
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError
        return validate_peer(value, port)
    except (httpx.HTTPError, ValueError, OSError):
        raise BrowserRefused("No compatible debugging browser was found on that port. This connection is optional: ask Junior to open a website and approve it, or start the dedicated debugging profile described in README.") from None


def validate_launch(arguments: list[str]):
    # Chrome's effective switches are the final value for each key; never combine overridden feature lists.
    switches = {arg.partition("=")[0]: arg.partition("=")[2] for arg in arguments if arg.startswith("--")}
    required = {arg.partition("=")[0]: arg.partition("=")[2] for arg in NETWORK_ARGS}
    disabled = set(switches.get("--disable-features", "").split(","))
    safe = all(switches.get(key) == value for key, value in required.items() if key != "--disable-features")
    safe = safe and set(required["--disable-features"].split(",")).issubset(disabled)
    safe = safe and "--enable-automation" in switches
    forbidden = {"--enable-quic", "--disable-web-security", "--ignore-certificate-errors", "--allow-file-access-from-files", "--no-proxy-server"}
    if not safe or forbidden.intersection(switches):
        raise BrowserRefused("This browser's launch options do not meet Junior's network protections. Use the documented dedicated debugging profile; personal browser settings were not changed.")
