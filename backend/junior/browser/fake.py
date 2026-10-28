"""FAKE_AI adapter: no real browser process or website/network access."""

import time
from uuid import uuid4

from junior.browser.runtime import BrowserManager, Snapshot, enabled
from junior.settings_store import get_setting


class FakePage:
    url = "about:blank"
    def is_closed(self):
        return False


class FakePeer:
    def is_connected(self):
        return True


class FakeBrowserManager(BrowserManager):
    def __init__(self):
        super().__init__()
        self.text = ""

    async def connect(self, port):
        enabled()
        if not get_setting("browser_sites"):
            from junior.browser.network import BrowserRefused
            raise BrowserRefused("Choose website origins before connecting a browser.")
        async with self.lock:
            await self.close()
            self.adapter, self.peer_port = "cdp", port
            self.started, self.sites = time.monotonic(), get_setting("browser_sites")
            self.browser = FakePeer()

    async def execute(self, spec, conversation_id=None, *, expected_generation=None):
        async with self.lock:
            if expected_generation is not None and expected_generation != self.generation:
                from junior.browser.network import BrowserRefused
                raise BrowserRefused("The browser session changed. Request a fresh approval.")
            self.validate(spec)
            if spec.kind == "navigate":
                self.page = FakePage()
                self.page.url = spec.url
                self.started = time.monotonic()
                self.sites = get_setting("browser_sites")
                self.epoch += 1
                return "Simulated browser navigation. No website was contacted. The page has not been read yet; take a snapshot to continue."
            self.snapshots[spec.snapshot_id].used = True
            if spec.kind == "fill":
                self.text = spec.text
            return f"Simulated browser {spec.kind}. No real website was changed."

    async def snapshot(self):
        self._current()
        data = {"tag": "INPUT", "type": "text", "name": "Research topic", "autocomplete": "", "role": "",
                "href": "", "disabled": False, "form": None, "html": "<input>"}
        snap = Snapshot(uuid4().hex, self.page.url, self.epoch, time.monotonic(), [None], [data])
        self.snapshots = {snap.id: snap}
        return {"id": snap.id, "url": self.page.url, "title": "Simulated research page", "text": self.text or "Browser fixture",
                "controls": [{"index": 0, **{k: v for k, v in data.items() if k != "html"}}]}
