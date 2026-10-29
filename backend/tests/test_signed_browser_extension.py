"""Exercise the unpacked extension in a disposable profile and a fake YouTube page."""
import asyncio
import base64
import contextlib
import json
import shutil
from pathlib import Path

import websockets
from playwright.async_api import async_playwright

from junior.browser.signed_bridge import EXTENSION_ID, EXTENSION_ORIGIN


def test_extension_pairs_and_only_controls_its_own_tab(tmp_path):
    async def check():
        connected = asyncio.get_running_loop().create_future()
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
        async def handler(ws):
            assert json.loads(await ws.recv()) == {"token": "x" * 43}
            await ws.send(json.dumps({"connected": True}))
            connected.set_result(ws)
            await ws.wait_closed()

        async with await asyncio.start_server(fixture_http, "127.0.0.1", 0) as http, websockets.serve(handler, "127.0.0.1", 0, origins=[EXTENSION_ORIGIN]) as server:
            port = server.sockets[0].getsockname()[1]
            fixture_origin = f"http://127.0.0.1:{http.sockets[0].getsockname()[1]}"
            extension = tmp_path / "extension"
            shutil.copytree(Path(__file__).resolve().parents[2] / "browser-extension", extension)
            worker = extension / "worker.js"
            source = worker.read_text(encoding="utf-8").replace("127.0.0.1:8000", f"127.0.0.1:{port}").replace("< 25000", "< 8000").replace("https://www.youtube.com", fixture_origin)
            worker.write_text(source, encoding="utf-8")
            async with async_playwright() as pw:
                context = await pw.chromium.launch_persistent_context(str(tmp_path / "profile"), channel="chromium", headless=True,
                    args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}", "--autoplay-policy=no-user-gesture-required"])
                unrelated = await context.new_page()
                await unrelated.goto(fixture_origin + "/watch?v=original001")
                popup = await context.new_page()
                await popup.goto(f"chrome-extension://{EXTENSION_ID}/popup.html")
                await popup.locator("#code").fill("x" * 43)
                await popup.locator("#pair").click()
                ws = await asyncio.wait_for(connected, 15)
                async def response():
                    while True:
                        message = json.loads(await ws.recv())
                        if message == {"ping": True}:
                            await ws.send(json.dumps({"pong": True}))
                            continue
                        return message
                await ws.send(json.dumps({"id": "a" * 32, "command": "media_play", "payload": {"video_id": "fakevideo01"}}))
                result = await asyncio.wait_for(response(), 35)
                diagnostics = []
                for page in context.pages:
                    if "fakevideo01" in page.url:
                        diagnostics.append(await page.evaluate("""() => {let v=document.querySelector('video'); return v ? {paused:v.paused,muted:v.muted,time:v.currentTime,error:v.error?.code} : {url:location.href,title:document.title,body:document.body?.innerText?.slice(0,100)}}"""))
                assert result["id"] == "a" * 32 and result["result"]["outcome"] == "sent", (result, diagnostics)
                assert not unrelated.is_closed() and unrelated.url.endswith("original001")
                await ws.send(json.dumps({"id": "b" * 32, "command": "media_stop", "payload": {}}))
                result = await asyncio.wait_for(response(), 10)
                assert result["id"] == "b" * 32 and result["result"]["outcome"] == "sent"
                assert not unrelated.is_closed()
                await ws.send(json.dumps({"id": "c" * 32, "command": "media_play", "payload": {"video_id": "fakevideo01"}}))
                result = await asyncio.wait_for(response(), 35)
                diagnostics = [(page.url, await page.evaluate("""() => {let v=document.querySelector('video'); return v ? {paused:v.paused, time:v.currentTime, error:v.error?.code} : null}""")) for page in context.pages]
                assert result["result"]["outcome"] == "sent", (result, diagnostics)
                owned = next(page for page in context.pages if "fakevideo01" in page.url)
                await owned.goto(fixture_origin + "/other")
                await ws.send(json.dumps({"id": "d" * 32, "command": "media_stop", "payload": {}}))
                result = await asyncio.wait_for(response(), 10)
                assert result["result"]["outcome"] == "failed" and not owned.is_closed()
                await ws.send(json.dumps({"id": "e" * 32, "command": "media_play", "payload": {"video_id": "fakevideo01"}}))
                await ws.send(json.dumps({"id": "f" * 32, "command": "media_stop", "payload": {}}))
                replies = [await asyncio.wait_for(response(), 15), await asyncio.wait_for(response(), 15)]
                assert {item["id"] for item in replies} == {"e" * 32, "f" * 32}
                await asyncio.sleep(1)
                assert not any("fakevideo01" in page.url and not page.is_closed() for page in context.pages)
                assert not owned.is_closed() and not unrelated.is_closed()
                await context.close()
    asyncio.run(check())
