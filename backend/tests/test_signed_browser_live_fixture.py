"""Real local backend and extension, using disposable data and a local video fixture."""
import asyncio
import base64
import contextlib
import json
import shutil
import socket
from pathlib import Path

import httpx
import uvicorn
import websockets
from playwright.async_api import async_playwright

from junior.browser.signed_bridge import EXTENSION_ID
from junior.config import get_settings
from junior.main import create_app


def test_junior_chat_through_paired_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AI", "true")
    get_settings.cache_clear()

    async def run():
        video = base64.b64encode((Path(__file__).parent / "fixtures" / "signed_browser_test.webm").read_bytes()).decode("ascii")
        html = f'<video src="data:video/webm;base64,{video}" autoplay loop></video>'.encode()
        async def fixture_http(reader, writer):
            try:
                await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: " + str(len(html)).encode() + b"\r\nConnection: close\r\n\r\n" + html)
                await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionResetError, TimeoutError):
                pass
            finally:
                writer.close()
                with contextlib.suppress(ConnectionResetError):
                    await writer.wait_closed()

        async with await asyncio.start_server(fixture_http, "127.0.0.1", 0) as fixture:
            fixture_origin = f"http://127.0.0.1:{fixture.sockets[0].getsockname()[1]}"
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            app = create_app()
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on", timeout_graceful_shutdown=5))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                for _ in range(200):
                    if server.started:
                        break
                    await asyncio.sleep(0.1)
                assert server.started
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=40) as client:
                    assert (await client.put("/api/computer/browser", json={"enabled": True, "sites": ["*"]})).status_code == 200
                    code = (await client.post("/api/computer/signed-browser/pair")).json()["pairing_code"]
                    assert (await client.put("/api/computer/signed-browser/media", json={"enabled": True})).status_code == 200
                    extension = tmp_path / "extension"
                    shutil.copytree(Path(__file__).resolve().parents[2] / "browser-extension", extension)
                    worker = extension / "worker.js"
                    source = worker.read_text(encoding="utf-8").replace("127.0.0.1:8000", f"127.0.0.1:{port}").replace("https://www.youtube.com", fixture_origin)
                    worker.write_text(source, encoding="utf-8")
                    async with async_playwright() as pw:
                        context = await pw.chromium.launch_persistent_context(str(tmp_path / "profile"), channel="chromium", headless=True,
                            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}", "--autoplay-policy=no-user-gesture-required"])
                        try:
                            unrelated = await context.new_page()
                            await unrelated.goto(fixture_origin + "/watch?v=original001")
                            popup = await context.new_page()
                            await popup.goto(f"chrome-extension://{EXTENSION_ID}/popup.html")
                            await popup.locator("#code").fill(code)
                            await popup.locator("#pair").click()
                            for _ in range(100):
                                if (await client.get("/api/computer/signed-browser")).json()["connected"]:
                                    break
                                await asyncio.sleep(0.1)
                            assert (await client.get("/api/computer/signed-browser")).json()["connected"]
                            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/chat") as chat:
                                await chat.send(json.dumps({"type": "message", "text": "play the song blue eyes", "conversation_id": None}))
                                cards = []
                                while True:
                                    event = json.loads(await asyncio.wait_for(chat.recv(), 45))
                                    if event["type"] == "approval": cards.append(event["item"])
                                    if event["type"] in {"done", "error"}: break
                                assert event["type"] == "done" and "Chrome tab" in event["text"]
                                assert len(cards) == 1 and cards[0]["status"] == "posted"
                                assert not unrelated.is_closed()
                                await chat.send(json.dumps({"type": "message", "text": "stop the song", "conversation_id": event["conversation_id"]}))
                                while True:
                                    event = json.loads(await asyncio.wait_for(chat.recv(), 20))
                                    if event["type"] in {"done", "error"}: break
                                assert "Stopped" in event["text"] and not unrelated.is_closed()
                                conversation = event["conversation_id"]
                                await client.put("/api/permissions/mode", json={"mode": "ask_all"})
                                await chat.send(json.dumps({"type": "message", "text": "play the song blue eyes", "conversation_id": conversation}))
                                cards = []
                                while True:
                                    event = json.loads(await asyncio.wait_for(chat.recv(), 20))
                                    if event["type"] == "approval": cards.append(event["item"])
                                    if event["type"] in {"done", "error"}: break
                                assert len(cards) == 1 and cards[0]["status"] == "waiting"
                                approved = await client.post(f"/api/approvals/{cards[0]['id']}/approve", json={})
                                assert approved.json()["status"] == "posted"
                        finally:
                            await context.close()
            finally:
                if server.started:
                    await app.state.signed_browser.disconnect()
                server.should_exit = True
                try:
                    await asyncio.wait_for(serving, 15)
                except TimeoutError:
                    serving.cancel()
                    await asyncio.gather(serving, return_exceptions=True)
    try:
        asyncio.run(run())
    finally:
        get_settings.cache_clear()
