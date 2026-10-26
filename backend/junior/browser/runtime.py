"""One bounded, temporary Chromium context. Page data is never an authorization source."""

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from junior.browser.network import BrowserRefused, ScopedProxy, checked_url
from junior.computer.jobs import redact
from junior.pause import is_paused
from junior.permissions import get_mode
from junior.settings_store import get_setting

PROTECTED = re.compile(r"(?i)\b(?:password|passcode|passkey|credential|otp|2fa|mfa|one[ -]time[ -]code|cc-[a-z]+|sign[ -]?in|log[ -]?in|credit card|card number|cvv|pay|payment|checkout|billing|wallet|bank|purchase|buy|place order|complete order|confirm order|delete|remove|security settings|api key|secret|access token)\b")
DESCRIBE = """el => ({tag:el.tagName, type:el.type||'', role:el.getAttribute('role')||'',
name:(el.getAttribute('aria-label')||el.labels?.[0]?.innerText||el.innerText||el.getAttribute('placeholder')||'').slice(0,240),
href:el.getAttribute('href')||'', autocomplete:el.autocomplete||'', disabled:!!el.disabled,
form:el.form ? {action:el.form.action,method:el.form.method} : null,
html:el.outerHTML.slice(0,3000)})"""


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str
    url: str = Field(default="", max_length=2000)
    snapshot_id: str = Field(default="", max_length=32)
    element: int = Field(default=-1, ge=-1, le=59)
    text: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_action(self):
        if self.kind not in {"navigate", "click", "fill", "download"}:
            raise ValueError("Choose navigate, click, fill or download.")
        if self.kind == "navigate":
            if not self.url or self.snapshot_id or self.element != -1 or self.text:
                raise ValueError("Navigation takes only a URL.")
        elif not re.fullmatch(r"[a-f0-9]{32}", self.snapshot_id) or self.element < 0 or self.url:
            raise ValueError("Use an element and snapshot returned by browser_snapshot.")
        if self.kind != "fill" and self.text:
            raise ValueError("Text belongs only to a fill action.")
        from junior.senders.guard import NEVER_SEND
        if any(pattern.search(self.text) for pattern, _ in NEVER_SEND) or re.search(r"\bAIza[\w-]{25,}", self.text):
            raise ValueError("Secrets cannot be entered through browser tools.")
        if any(ord(c) < 32 and c not in "\n\t" for c in self.text):
            raise ValueError("Unsupported control characters in browser text.")
        return self


def enabled():
    if not get_setting("computer_enabled") or not get_setting("browser_enabled"):
        raise BrowserRefused("Browser controls are off. Enable them and choose websites in Settings → Computer.")
    if is_paused() or get_mode() == "plan":
        raise BrowserRefused("Junior is paused or in Plan mode; browser sessions cannot act.")


def target_allowed(data, spec):
    if data["disabled"] or data["type"] in {"password", "file", "hidden"} or PROTECTED.search(" ".join(str(data[k]) for k in ("name", "type", "autocomplete"))):
        raise BrowserRefused("Authentication, secrets, payments and protected account controls are not automated.")
    if spec.kind == "fill" and (data["tag"] not in {"INPUT", "TEXTAREA"} or data["type"] not in {"text", "email", "search", "url", "tel", "textarea", ""}):
        raise BrowserRefused("Fill is supported only for ordinary text fields, never files/passwords.")
    if spec.kind == "download" and data["tag"] != "A":
        raise BrowserRefused("Download must use an observed link.")


@dataclass
class Snapshot:
    id: str
    url: str
    epoch: int
    created: float
    handles: list
    controls: list
    used: bool = False


class BrowserManager:
    def __init__(self):
        self.pw = self.browser = self.context = self.page = self.proxy = None
        self.lock = asyncio.Lock()
        self.close_lock = asyncio.Lock()
        self.snapshots = {}
        self.started = 0
        self.epoch = 0
        self.sites = []
        self.monitor = None
        self.action = None
        self.downloads = []
        self.requests = 0

    def network_active(self):
        try:
            enabled()
            return self.sites == get_setting("browser_sites") and time.monotonic() - self.started < 900
        except BrowserRefused:
            return False

    def status(self):
        return {"connected": self.page is not None and not self.page.is_closed(), "adapter": "isolated",
                "url": redact(self.page.url) if self.page else "", "downloads": self.downloads[-10:],
                "expires_seconds": max(0, int(900 - (time.monotonic() - self.started))) if self.page else 0}

    async def _launch(self):
        from playwright.async_api import async_playwright
        self.sites = get_setting("browser_sites")
        if not self.sites:
            raise BrowserRefused("Choose at least one exact website origin in Settings → Computer → Browser.")
        self.started = time.monotonic()
        self.proxy = ScopedProxy(self.sites, self.network_active)
        try:
            proxy = await self.proxy.start()
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(headless=True, proxy=proxy, args=[
                "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--disable-features=WebTransport,WebUSB,WebBluetooth,Serial,DirectSockets",
                "--disable-background-networking", "--disable-extensions"])
            self.context = await self.browser.new_context(accept_downloads=True, service_workers="block",
                                                         permissions=[], viewport={"width": 1280, "height": 800})
            await self.context.route("**/*", self._route)
            await self.context.route_web_socket("**/*", lambda ws: ws.close())
            self.page = await self.context.new_page()
            self.page.set_default_timeout(7000)
            self.page.set_default_navigation_timeout(15000)
            self.page.on("framenavigated", lambda frame: self._navigated(frame))
            self.page.on("dialog", lambda dialog: dialog.dismiss())
            self.page.on("download", lambda download: download.cancel() if self.action != "download" else None)
            self.context.on("page", lambda page: page.close() if page != self.page else None)
            self.monitor = asyncio.create_task(self._watch())
        except BaseException:
            await self.close()
            raise

    def _navigated(self, frame):
        if self.page and frame == self.page.main_frame:
            self.epoch += 1

    async def _route(self, route):
        request = route.request
        try:
            checked_url(request.url, self.sites)
            if not self.network_active() or self.requests >= 300:
                raise BrowserRefused("Browser request limit reached.")
            if request.method not in {"GET", "HEAD", "OPTIONS"} and self.action not in {"click", "fill"}:
                raise BrowserRefused("A form request requires an approved input action.")
            if request.resource_type in {"media", "websocket"}:
                raise BrowserRefused("Streaming media/websocket channels are disabled.")
            self.requests += 1
            await route.continue_()
        except BrowserRefused:
            await route.abort("blockedbyclient")

    async def _watch(self):
        try:
            while self.network_active():
                await asyncio.sleep(1)
            await self.close()
        except asyncio.CancelledError:
            pass

    async def close(self):
        async with self.close_lock:
            await self._close_owned()

    async def _close_owned(self):
        monitor, self.monitor = self.monitor, None
        if monitor and monitor != asyncio.current_task():
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        self.page = None
        self.snapshots.clear()
        for name in ("context", "browser", "pw", "proxy"):
            obj = getattr(self, name)
            setattr(self, name, None)
            if obj:
                try:
                    await asyncio.wait_for(obj.stop() if name == "pw" else obj.close(), 5)
                except Exception:
                    pass
        self.requests = 0

    async def disconnect(self):
        # Serialize owner/config disconnect with startup/input; no late context can be created after disconnect.
        async with self.lock:
            await self.close()

    def _current(self):
        enabled()
        if not self.page or self.page.is_closed() or not self.network_active():
            raise BrowserRefused("No active isolated browser. Ask to navigate to an allowed website first.")
        checked_url(self.page.url, self.sites)
        from urllib.parse import urlsplit
        if re.search(r"(?i)/(?:login|signin|oauth|auth|checkout|payment|billing)(?:/|$)", urlsplit(self.page.url).path):
            raise BrowserRefused("Finish authentication, payment and account-security pages yourself.")

    async def snapshot(self):
        from playwright.async_api import Error as PlaywrightError
        try:
            async with asyncio.timeout(12):
                return await self._snapshot()
        except (PlaywrightError, TimeoutError):
            raise BrowserRefused("The page could not be observed in time. No input was attempted.") from None

    async def _snapshot(self):
        async with self.lock:
            self._current()
            title = await self.page.evaluate("() => document.title.slice(0, 300)")
            if PROTECTED.search(title):
                raise BrowserRefused("This is an authentication/payment/security page; finish it yourself.")
            url, epoch = self.page.url, self.epoch
            handles = []
            controls = []
            # Fixed internal DOM extraction only; there is no arbitrary evaluate/JavaScript tool.
            array = await self.page.evaluate_handle("() => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role=button]')).slice(0,120)")
            properties = await array.get_properties()
            await array.dispose()
            for prop in properties.values():
                handle = prop.as_element()
                if handle is None:
                    await prop.dispose()
                    continue
                if len(handles) >= 60 or not await handle.is_visible():
                    await handle.dispose()
                    continue
                data = await handle.evaluate(DESCRIBE)
                if data["type"] == "password" or PROTECTED.search(data["autocomplete"]):
                    data["name"] = "[protected field]"
                handles.append(handle)
                controls.append(data)
            text = await self.page.locator("body").evaluate("el => el.innerText.slice(0,12000)")
            if self.page.url != url or self.epoch != epoch:
                raise BrowserRefused("The page navigated during observation. Observe again.")
            snap = Snapshot(uuid4().hex, url, epoch, time.monotonic(), handles, controls)
            for old in self.snapshots.values():
                for handle in old.handles:
                    await handle.dispose()
            self.snapshots = {snap.id: snap}
            return {"id": snap.id, "url": redact(url), "title": redact(title), "text": redact(text),
                    "controls": [{"index": i, **{k: redact(str(v)) if isinstance(v, str) else v for k, v in data.items() if k != "html"}}
                                 for i, data in enumerate(controls)]}

    def validate(self, spec):
        enabled()
        if spec.kind == "navigate":
            checked_url(spec.url, get_setting("browser_sites"))
            return {"target_label": spec.url}
        self._current()
        snap = self.snapshots.get(spec.snapshot_id)
        if not snap or snap.used or time.monotonic() - snap.created > 600 or snap.epoch != self.epoch or snap.url != self.page.url:
            raise BrowserRefused("That browser snapshot is expired, used or changed. Take a fresh snapshot.")
        if spec.element >= len(snap.handles):
            raise BrowserRefused("That element was not observed.")
        data = snap.controls[spec.element]
        target_allowed(data, spec)
        return {"target_label": data["name"] or data["tag"], "page_url": snap.url,
                "form": data["form"], "target_href": data["href"]}

    async def execute(self, spec, conversation_id=None):
        from playwright.async_api import Error as PlaywrightError
        async with self.lock:
            self.validate(spec)
            attempted = False
            try:
                if not self.page:
                    await self._launch()
                self.action = spec.kind
                if spec.kind == "navigate":
                    attempted = True
                    await self.page.goto(spec.url, wait_until="domcontentloaded")
                    checked_url(self.page.url, self.sites)
                    return f"Opened {redact(self.page.url)}. Take a browser snapshot to inspect the result."
                snap = self.snapshots[spec.snapshot_id]
                handle = snap.handles[spec.element]
                current = await handle.evaluate(DESCRIBE)
                if current != snap.controls[spec.element] or not await handle.is_visible() or not await handle.is_enabled():
                    raise BrowserRefused("The reviewed browser target changed. Observe again before acting.")
                target_allowed(current, spec)
                if current["form"]:
                    checked_url(current["form"]["action"], self.sites)
                enabled()
                self.validate(spec)
                snap.used = True  # one attempt, including an ambiguous timeout
                attempted = True
                if spec.kind == "fill":
                    await handle.fill(spec.text)
                elif spec.kind == "download":
                    async with self.page.expect_download(timeout=10000) as pending:
                        await handle.click()
                    download = await pending.value
                    file = await asyncio.wait_for(download.path(), 20)
                    if not file or not 0 < Path(file).stat().st_size <= 20 * 1024 * 1024:
                        await download.cancel()
                        raise BrowserRefused("Download was empty or exceeded 20 MB.")
                    from junior.files import save_received, safe_name
                    import mimetypes
                    name = safe_name(download.suggested_filename)
                    file_id, tag = save_received(Path(file).read_bytes(), name, mimetypes.guess_type(name)[0] or "application/octet-stream",
                                                 "browser", conversation_id, library_folder="Downloads")
                    self.downloads.append({"file_id": file_id, "name": name, "url": f"/api/files/{file_id}/download"})
                    await download.delete()
                    return f"Downloaded {tag} to the Downloads gallery. It was saved without opening or running it."
                else:
                    await handle.click()
                return f"Browser accepted {spec.kind}. Take a new snapshot to verify the page outcome before another action."
            except asyncio.CancelledError:
                # A cancelled approval cannot leave a delayed browser input alive behind the dashboard.
                await self.close()
                raise
            except BrowserRefused:
                raise
            except (PlaywrightError, TimeoutError, OSError):
                if attempted:
                    raise RuntimeError("Browser action may have partly happened. Inspect the page; it will not be retried automatically.") from None
                raise BrowserRefused("Chromium could not start. Install the pinned Playwright browser with the documented setup command.") from None
            finally:
                self.action = None
