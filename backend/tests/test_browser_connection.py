"""Explicit debugging connection, network policy, owned-context isolation and preservation of existing pages."""

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from junior.browser import cdp, runtime
from junior.browser.cdp import NETWORK_ARGS, validate_launch, validate_peer
from junior.browser.network import BrowserRefused, ScopedProxy
from junior.browser.runtime import BrowserAction, BrowserManager
from junior.settings_store import set_setting
from test_browser import client, enable, card, approve  # noqa: F401


PEER = {"Browser": "Chrome/149.0.0.0", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/01234567-89ab-cdef-0123-456789abcdef"}


@pytest.mark.parametrize("value", ["ws://example.com:9222/devtools/browser/01234567-89ab-cdef", "ws://127.0.0.1:8000/devtools/browser/01234567-89ab-cdef",
                                 "ws://127.0.0.1:9222/devtools/page/01234567-89ab-cdef", "ws://user:pw@127.0.0.1:9222/devtools/browser/01234567-89ab-cdef",
                                 "ws://127.0.0.1:9222/devtools/browser/01234567-89ab-cdef?token=hidden", "file:///private"])
def test_reject_remote_or_wrong_cdp_endpoints(value):
    with pytest.raises(BrowserRefused):
        validate_peer({**PEER, "webSocketDebuggerUrl": value}, 9222)


def test_valid_endpoint_and_effective_flags():
    assert validate_peer(PEER, 9222) == PEER["webSocketDebuggerUrl"]
    validate_launch(["chrome.exe", "--enable-automation", *NETWORK_ARGS])
    with pytest.raises(BrowserRefused):
        validate_launch(["--enable-automation", *NETWORK_ARGS, "--disable-features=OtherOnly"])


@pytest.mark.parametrize("flag", ["--disable-web-security", "--ignore-certificate-errors", "--allow-file-access-from-files", "--enable-quic", "--no-proxy-server"])
def test_unsafe_launch_flags_are_not_attached(flag):
    with pytest.raises(BrowserRefused):
        validate_launch(["--enable-automation", *NETWORK_ARGS, flag])


def test_connect_is_owner_only_local_config_and_invalidates_cards(client):
    c = client
    assert c.post("/api/computer/browser/connect", json={"port": 9222}).status_code == 409
    assert c.post("/api/computer/browser/connect", json={"port": 9222, "url": "http://remote.example"}).status_code == 422
    assert c.post("/api/computer/browser/connect", json={"port": 80}).status_code == 422
    enable(c)
    old = card(c, BrowserAction(kind="navigate", url="https://example.com"))
    status = c.post("/api/computer/browser/connect", json={"port": 9222}).json()
    assert status["adapter"] == "cdp" and status["transport_connected"] and not status["connected"]
    assert approve(c, old)["status"] != "posted"
    fresh = card(c, BrowserAction(kind="navigate", url="https://example.com"))
    assert approve(c, fresh)["status"] == "posted"
    result = c.post("/api/computer/browser/disconnect").json()
    assert not result["transport_connected"] and result["adapter"] == "isolated"


@pytest.mark.parametrize("adapter", ["native", "fake"])
def test_waiting_input_rechecks_session_identity_under_lock(adapter):
    from junior.browser.fake import FakeBrowserManager
    async def run():
        manager = BrowserManager() if adapter == "native" else FakeBrowserManager()
        before = manager.generation
        await manager.lock.acquire()
        task = asyncio.create_task(manager.execute(BrowserAction(kind="navigate", url="https://example.com"), expected_generation=before))
        await asyncio.sleep(0)
        manager.generation = "new-session"
        manager.lock.release()
        with pytest.raises(BrowserRefused, match="session changed"):
            await task
        assert manager.page is None
    asyncio.run(run())


def test_native_attach_preserves_existing_page_and_uses_scoped_proxy(monkeypatch):
    from playwright.async_api import async_playwright
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<title>Connected fixture</title><p>Owned browser session</p>")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    class FixtureProxy(ScopedProxy):
        async def resolve(self, host, port):
            assert host == "fixture.example"
            return "8.8.8.8"
        async def dial(self, ip, port):
            assert ip == "8.8.8.8"
            return await asyncio.open_connection("127.0.0.1", server.server_port)
    monkeypatch.setattr(runtime, "ScopedProxy", FixtureProxy)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        debug_port = probe.getsockname()[1]
    set_setting("browser_enabled", True)
    set_setting("browser_sites", ["http://fixture.example"])

    async def run():
        async with async_playwright() as pw:
            # Owned throwaway debugging browser; no user's browser/profile is accessed by this test.
            peer = await pw.chromium.launch(headless=True, args=[*NETWORK_ARGS, "--enable-automation", f"--remote-debugging-port={debug_port}", "--remote-debugging-address=127.0.0.1"])
            existing = await peer.new_context()
            page = await existing.new_page()
            await page.set_content("<p>Existing page must stay intact</p>")
            await existing.add_cookies([{"name": "owner_fixture", "value": "not-a-secret", "url": "http://fixture.example"}])
            browser = BrowserManager()
            try:
                await browser.connect(debug_port)
                assert browser.status()["adapter"] == "cdp" and browser.page is None
                await browser.execute(BrowserAction(kind="navigate", url="http://fixture.example"))
                result = await browser.snapshot()
                assert "Owned browser session" in result["text"]
                assert not await browser.context.cookies(), "Existing context cookies must never be imported"
                await browser.disconnect()
                assert peer.is_connected() and not page.is_closed()
                assert await page.locator("p").inner_text() == "Existing page must stay intact"
            finally:
                await browser.close()
                await peer.close()
        await asyncio.sleep(.1)
    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
