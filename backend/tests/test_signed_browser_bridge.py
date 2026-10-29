import asyncio
import json
from types import SimpleNamespace

from junior.browser.signed_bridge import (
    EXTENSION_ORIGIN, SignedBrowserBridge, issue_pairing_code, local_peer, paired, revoke_pairing,
)
from junior.settings_store import all_settings


def test_pairing_rotation_and_private_setting():
    first = issue_pairing_code()
    assert paired(first) and not paired("wrong")
    assert first not in repr(all_settings())
    second = issue_pairing_code()
    assert first != second and paired(second) and not paired(first)
    revoke_pairing()
    assert not paired(second)


def test_only_real_loopback_peers_are_accepted():
    assert local_peer("127.0.0.1") and local_peer("::1")
    assert not local_peer("192.168.1.5") and not local_peer("testclient") and not local_peer(None)


class Socket:
    def __init__(self, host="127.0.0.1", origin=EXTENSION_ORIGIN):
        self.client = SimpleNamespace(host=host)
        self.headers = {"origin": origin}
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.accepted = False
        self.closed = False
    async def accept(self):
        self.accepted = True
    async def receive_text(self):
        return await self.incoming.get()
    async def send_json(self, value):
        await self.outgoing.put(value)
    async def close(self, code=1000):
        self.closed = True


def test_origin_authentication_and_correlated_command():
    async def check():
        bridge = SignedBrowserBridge()
        bad = Socket(origin="https://evil.example")
        await bridge.serve(bad)
        assert bad.closed and not bad.accepted and not bridge.connected
        secret = issue_pairing_code()
        socket = Socket()
        await socket.incoming.put(json.dumps({"token": secret}))
        serving = asyncio.create_task(bridge.serve(socket))
        assert await asyncio.wait_for(socket.outgoing.get(), 2) == {"connected": True}
        task = asyncio.create_task(bridge.command("media_play", {"video_id": "fakevideo01"}))
        command = await asyncio.wait_for(socket.outgoing.get(), 2)
        assert command["command"] == "media_play"
        await socket.incoming.put(json.dumps({"id": "different", "result": {"outcome": "sent"}}))
        await socket.incoming.put(json.dumps({"id": command["id"], "result": {"outcome": "sent"}}))
        assert (await asyncio.wait_for(task, 2))["outcome"] == "sent"
        await socket.incoming.put(json.dumps({"unpair": True}))
        await asyncio.wait_for(serving, 2)
        assert socket.closed and not bridge.connected
        assert not paired(secret)
    asyncio.run(check())


def test_pairing_endpoints_are_local_and_exclude_forwarded_requests(monkeypatch):
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    import pytest
    from junior.config import get_settings
    from junior.main import create_app
    monkeypatch.setenv("FAKE_AI", "true")
    get_settings.cache_clear()
    with TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50100)) as client:
        assert client.get("/api/computer/signed-browser", headers={"x-forwarded-for": "198.51.100.5"}).status_code == 403
        response = client.post("/api/computer/signed-browser/pair")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        token = response.json()["pairing_code"]
        assert token not in client.get("/api/settings").text
        assert client.put("/api/computer/signed-browser/media", json={"enabled": True}).json()["media_enabled"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://127.0.0.1:8000/api/computer/signed-browser/ws", headers={"origin": "https://evil.example"}):
                pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://127.0.0.1:8000/api/computer/signed-browser/ws", headers={"origin": EXTENSION_ORIGIN, "x-forwarded-for": "198.51.100.5"}):
                pass
        with client.websocket_connect("ws://127.0.0.1:8000/api/computer/signed-browser/ws", headers={"origin": EXTENSION_ORIGIN}) as ws:
            ws.send_json({"token": token})
            assert ws.receive_json() == {"connected": True}
            assert client.get("/api/computer/signed-browser").json()["connected"]
    get_settings.cache_clear()


def test_signed_media_uses_only_paired_bridge_and_owned_stop():
    from junior.browser.media import Player
    from junior.settings_store import set_setting

    class Bridge:
        connected = True
        calls = []
        async def command(self, name, payload, timeout=30):
            self.calls.append((name, payload))
            return {"outcome": "sent", "state": "playing"}

    async def check():
        set_setting("browser_enabled", True)
        set_setting("browser_sites", ["*"])
        set_setting("signed_browser_media", True)
        bridge = Bridge()
        player = Player(signed_bridge=bridge)
        result = await player.play({"video_id": "fakevideo01", "title": "Example"})
        assert "Chrome tab" in result and player.signed_session
        await player.next()
        await player.stop_owned()
        assert [name for name, _ in bridge.calls if name != "media_status"] == ["media_play", "media_next", "media_stop"]
        assert not player.session
    asyncio.run(check())


def test_disconnected_signed_browser_never_falls_back_to_separate_player():
    import pytest
    from junior.browser.media import Player
    from junior.browser.network import BrowserRefused
    from junior.settings_store import set_setting
    async def check():
        set_setting("browser_enabled", True)
        set_setting("browser_sites", ["*"])
        set_setting("signed_browser_media", True)
        player = Player(signed_bridge=SimpleNamespace(connected=False))
        with pytest.raises(BrowserRefused, match="Connect the signed-in Chrome extension"):
            await player.play({"video_id": "fakevideo01", "title": "Example"})
        assert not player.session and player.browser is None
    asyncio.run(check())


def test_pause_interrupts_an_in_flight_signed_player():
    import pytest
    from junior.browser.media import Player, VerificationRequired
    from junior.settings_store import set_setting
    class Bridge:
        connected = True
        def __init__(self):
            self.started = asyncio.Event()
            self.calls = []
        async def command(self, name, payload, timeout=30):
            self.calls.append(name)
            if name == "media_play":
                self.started.set()
                await asyncio.Event().wait()
            return {"outcome": "sent"}
    async def check():
        set_setting("browser_enabled", True)
        set_setting("browser_sites", ["*"])
        set_setting("signed_browser_media", True)
        bridge = Bridge()
        player = Player(signed_bridge=bridge)
        task = asyncio.create_task(player.play({"video_id": "fakevideo01", "title": "Example"}))
        await asyncio.wait_for(bridge.started.wait(), 2)
        set_setting("paused", True)
        with pytest.raises(VerificationRequired, match="interrupted"):
            await asyncio.wait_for(task, 5)
        assert "media_stop" in bridge.calls and not player.session
    asyncio.run(check())
