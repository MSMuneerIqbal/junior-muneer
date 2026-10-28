"""A single, user-requested YouTube playback action with its own visible temporary player."""

import asyncio
import json
import re
import socket
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import select

from junior.browser.cdp import NETWORK_ARGS
from junior.browser.network import BrowserRefused, checked_url, public_address
from junior.db import ApprovalItem, Message, session_scope
from junior.pause import is_paused
from junior.permissions import get_mode, rule_for
from junior.senders.base import SendResult
from junior.settings_store import get_setting

HOSTS = ("youtube.com", "youtube-nocookie.com", "googlevideo.com", "ytimg.com", "google.com", "gstatic.com")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAY = re.compile(r"\b(play|bajao|baja|chalao|chala|lagao|lgao|lagado|laga|lga|sunao)\b|چلاؤ|چلا|بجاؤ|لگاؤ", re.I)
SONG = re.compile(r"\b(song|music|gaana|gana|geet|track|youtube)\b|گانا|گانے|موسیقی|یوٹیوب", re.I)
STOP = re.compile(r"\b(stop|close|quit|band|rok|roko)\b|بند|روک", re.I)
NEGATED = re.compile(r"\b(?:do\s+not|don['’]?t|never|not|mat|nahin|nahi)\b.{0,35}\b(?:play|bajao|baja|chalao|chala|lagao|lgao|lagado|laga|lga|sunao)\b|(?:نہ|مت).{0,35}(?:چلا|بجا|لگا)", re.I)
HOW_TO = re.compile(r"\b(?:how\s+(?:do|can|to)|why\s+(?:does|do|is)|kaise|kaisay|kyun)\b", re.I)
ROLE_PLAY = re.compile(r"\bplay\s+(?:the\s+)?role\b", re.I)
DISCUSSION = re.compile(r"^(?:please\s+)?(?:translate|summari[sz]e|explain|write|draft|describe|tell\s+me\s+about|what\s+is)\b", re.I)
PERSONAL_BROWSER = re.compile(r"\b(?:signed[ -]?in|logged[ -]?in|personal browser|my browser|my chrome)\b", re.I)
EXTRA_TASK = re.compile(r"\b(?:and|then|aur|phir)\b.{0,80}\b(?:send|email|write|create|save|download|upload|delete|message|search)\b", re.I)
STOPWORDS = {"play", "song", "music", "youtube", "kro", "karo", "krdo", "kr", "do", "yr", "yaar", "bhai", "wala", "wali", "ka", "ki", "ko", "on", "the", "please", "bajao", "baja", "chalao", "chala", "lagao", "laga", "lagado", "lga", "sunao", "gana", "gaana", "geet", "track"}


class VerificationRequired(RuntimeError):
    """The site asked the owner to complete its verification in the visible player."""


def is_request(text: str) -> bool:
    return bool(PLAY.search(text or "") and SONG.search(text or "") and not NEGATED.search(text)
                and not HOW_TO.search(text) and not ROLE_PLAY.search(text) and not DISCUSSION.search(text.strip())
                and not PERSONAL_BROWSER.search(text) and not EXTRA_TASK.search(text))


def is_stop_request(text: str) -> bool:
    return bool(STOP.search(text or "") and SONG.search(text or "") and not DISCUSSION.search(text.strip())
                and not re.search(r"\b(?:do\s+not|don['’]?t|never|mat|nahi|nahin)\b.{0,25}\b(?:stop|close|band|rok|roko)\b|(?:نہ|مت).{0,25}(?:بند|روک)", text, re.I))


def is_continue(text: str) -> bool:
    return bool(re.fullmatch(r"(?:continue|conitnue|contine|cont|aage|ag[ae]y)\s*[.!]?", (text or "").strip(), re.I))


def continuation(context, text: str):
    """Resume only the immediately preceding music request, without replaying an existing card."""
    if not is_continue(text) or context.conversation_id is None:
        return None
    with session_scope() as session:
        rows = session.scalars(select(Message).where(Message.conversation_id == context.conversation_id,
                              Message.source == "user", Message.id.not_in(context.user_message_ids))
                              .order_by(Message.id.desc()).limit(50)).all()
        source = next((row for row in rows if not is_continue(row.content)), None)
        if not source or not is_request(source.content):
            return None
        cards = session.scalars(select(ApprovalItem).where(ApprovalItem.conversation_id == context.conversation_id,
                                ApprovalItem.action_type == "computer.media.play").order_by(ApprovalItem.id.desc())).all()
        existing = next((card for card in cards if card.meta.get("media_user_message_id") == source.id), None)
        if existing:
            if existing.status == "waiting":
                return {"reply": "The song is already on an approval card. Approve it once to start playback."}
            if existing.status == "posted":
                return {"reply": "That song was already started. Ask for it again if you want to replay it."}
            return {"reply": "The previous playback did not complete or needs checking. Check its card before trying again."}
        return {"text": source.content, "id": source.id}


def terms(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W_]+", text.casefold()) if len(word) > 1 and word not in STOPWORDS]


def matches_request(text: str, title: str) -> bool:
    wanted, actual = terms(text), terms(title)
    if not wanted:
        return False
    matches = sum(any(a == w or (len(w) >= 4 and (a.startswith(w) or w.startswith(a))) for a in actual) for w in wanted)
    return matches >= max(1, (len(wanted) + 1) // 2)


def videos(value):
    if isinstance(value, dict):
        item = value.get("videoRenderer")
        if isinstance(item, dict):
            yield item
        for child in value.values():
            yield from videos(child)
    elif isinstance(value, list):
        for child in value:
            yield from videos(child)


async def search(text: str) -> tuple[str, str]:
    if not terms(text):
        raise BrowserRefused("Tell me the song or artist you want to play.")
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        async with client.stream("GET", "https://www.youtube.com/results", params={"search_query": text[:300]}) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 5_000_000:
                    raise BrowserRefused("YouTube search returned too much data.")
                chunks.append(chunk)
    raw = b"".join(chunks).decode("utf-8", "replace")
    match = re.search(r"var ytInitialData\s*=\s*(\{.*?\});", raw)
    if not match:
        if "unusual traffic" in raw.casefold() or "recaptcha" in raw.casefold():
            raise BrowserRefused("YouTube requested verification during search. Try again later or open YouTube yourself.")
        raise BrowserRefused("YouTube search did not return usable results.")
    for video in videos(json.loads(match.group(1))):
        ident = video.get("videoId", "")
        title = "".join(part.get("text", "") for part in video.get("title", {}).get("runs", []))[:250]
        if VIDEO_ID.fullmatch(ident) and matches_request(text, title):
            return ident, title
    raise BrowserRefused("I couldn't find a YouTube video matching your request.")


def enabled():
    if not get_setting("computer_enabled") or not get_setting("browser_enabled"):
        raise BrowserRefused("Turn on browser controls in Settings → Computer first.")
    if is_paused() or get_mode("dashboard") == "plan":
        raise BrowserRefused("Junior is paused or in Plan mode.")
    checked_url("https://www.youtube.com/", get_setting("browser_sites"))


def authorized(item) -> bool:
    ident = item.meta.get("media_user_message_id")
    if not isinstance(ident, int):
        return False
    try:
        payload = json.loads(item.text)
        with session_scope() as session:
            message = session.get(Message, ident)
            if not message or message.source != "user" or message.conversation_id != item.conversation_id:
                return False
            if item.action_type == "computer.media.stop":
                return payload == {"stop": True} and is_stop_request(message.content) and bool(item.meta.get("media_session"))
            return bool(set(payload) == {"video_id", "title"} and VIDEO_ID.fullmatch(payload["video_id"])
                        and is_request(message.content) and matches_request(message.content, payload["title"]))
    except (ValueError, TypeError, KeyError):
        return False


async def prepare(context, text: str) -> str:
    from junior.computer.tools import queue_action
    try:
        enabled()
        from junior.privacy import credential_present
        if len(text) > 300 or credential_present(text):
            raise BrowserRefused("Send just the song title and artist, without sensitive information.")
        if not is_request(text) or not context.user_message_ids:
            raise BrowserRefused("Ask for a song to play in your own message.")
        with session_scope() as session:
            source = session.scalar(select(Message.id).where(Message.id.in_(context.user_message_ids),
                                    Message.conversation_id == context.conversation_id, Message.source == "user",
                                    Message.content == text).order_by(Message.id.desc()).limit(1))
        if not source:
            raise BrowserRefused("I couldn't verify the original song request.")
        from junior.config import get_settings
        if get_settings().fake_ai:
            ident, title = "fakevideo01", "Simulated " + " ".join(terms(text))
        else:
            ident, title = await search(text)
        body = json.dumps({"video_id": ident, "title": title}, ensure_ascii=False)
        return await queue_action(context, "computer.media.play", "media", body, f"Play on YouTube: {title}",
                                  {"op": "media_play", "media_user_message_id": source, "seconds": 60})
    except BrowserRefused as error:
        return f"NOT done: {error}"
    except (httpx.HTTPError, ValueError, RecursionError):
        return "NOT done: YouTube search is unavailable. Try again later."


def active_player():
    from junior.senders.registry import CURRENT
    sender = CURRENT.for_action("computer.media.stop")
    return sender.player if sender and sender.player.session else None


async def prepare_stop(context, text: str) -> str:
    from junior.computer.tools import queue_action
    try:
        enabled()
        player = active_player()
        if not player:
            return "NOT done: Junior's YouTube player is not open."
        with session_scope() as session:
            source = session.scalar(select(Message.id).where(Message.id.in_(context.user_message_ids),
                                    Message.conversation_id == context.conversation_id, Message.source == "user",
                                    Message.content == text).order_by(Message.id.desc()).limit(1))
        if not source or not is_stop_request(text):
            raise BrowserRefused("I couldn't verify the request to stop the player.")
        return await queue_action(context, "computer.media.stop", "media", json.dumps({"stop": True}),
                                  "Stop Junior's YouTube player", {"op": "media_stop",
                                  "media_user_message_id": source, "media_session": player.session})
    except BrowserRefused as error:
        return f"NOT done: {error}"


class Player:
    def __init__(self, fake=False):
        self.fake = fake
        self.pw = self.browser = self.context = self.page = self.watch = None
        self.lock = asyncio.Lock()
        self.video_id = ""
        self.session = ""

    async def close(self):
        watch, self.watch = self.watch, None
        if watch and watch != asyncio.current_task():
            watch.cancel()
            await asyncio.gather(watch, return_exceptions=True)
        for name in ("context", "browser", "pw"):
            obj = getattr(self, name)
            setattr(self, name, None)
            if obj:
                try:
                    await asyncio.wait_for(obj.stop() if name == "pw" else obj.close(), 5)
                except Exception:
                    pass
        self.page = None
        self.video_id = ""
        self.session = ""

    async def _watch(self):
        deadline = time.monotonic() + 900
        try:
            while self.page and not self.page.is_closed() and time.monotonic() < deadline:
                enabled()
                if rule_for("computer.media.play") == "deny" or rule_for("computer.browser.input") == "deny":
                    break
                url = urlsplit(self.page.url)
                if url.path == "/watch" and parse_qs(url.query).get("v", [""])[0] != self.video_id:
                    break  # do not automatically play a different video
                await asyncio.sleep(1)
        except (BrowserRefused, asyncio.CancelledError):
            pass
        finally:
            await self.close()

    async def play(self, payload):
        async with self.lock:
            enabled()
            await self.close()
            self.session = uuid4().hex
            if self.fake:
                return "Simulated playback; no real song played."
            from playwright.async_api import async_playwright
            try:
                self.pw = await async_playwright().start()
                self.video_id = payload["video_id"]
                self.browser = await self.pw.chromium.launch(headless=False,
                    args=NETWORK_ARGS + ["--autoplay-policy=no-user-gesture-required"],
                    ignore_default_args=["--mute-audio"])
                self.context = await self.browser.new_context(service_workers="block", permissions=[])
                validated_hosts = set()
                async def route(request_route):
                    req = request_route.request
                    host = (urlsplit(req.url).hostname or "").lower()
                    if (req.url.startswith("https://") and req.method in {"GET", "HEAD", "OPTIONS", "POST"}
                            and any(host == domain or host.endswith("." + domain) for domain in HOSTS)):
                        try:
                            if host not in validated_hosts:
                                rows = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM), 5)
                                if not rows or any(not public_address(row[4][0]) for row in rows):
                                    raise ValueError("non-public address")
                                validated_hosts.add(host)
                            await request_route.continue_()
                        except (OSError, ValueError, TimeoutError):
                            await request_route.abort()
                    else:
                        await request_route.abort()
                await self.context.route("**/*", route)
                await self.context.route_web_socket("**/*", lambda ws: ws.close())
                self.page = await self.context.new_page()
                self.context.on("page", lambda page: page.close() if page != self.page else None)
                await self.page.goto("https://www.youtube.com/watch?v=" + payload["video_id"], wait_until="commit", timeout=30000)
                await self.page.wait_for_function("""() => {
                    const v = document.querySelector('video');
                    const challenge = location.hostname === 'www.google.com' && location.pathname.startsWith('/sorry/');
                    return challenge || (v && !v.paused && !v.muted && v.volume > 0 && v.currentTime > 1);
                }""", timeout=30000)
                if urlsplit(self.page.url).hostname == "www.google.com" and urlsplit(self.page.url).path.startswith("/sorry/"):
                    self.watch = asyncio.create_task(self._watch())
                    raise VerificationRequired("YouTube requested verification. Complete it in the visible player; playback is not confirmed.")
                enabled()
                self.watch = asyncio.create_task(self._watch())
                return f"The YouTube player is running for: {payload['title']}. An ad may play first, and PC audio settings affect what you hear."
            except VerificationRequired:
                raise
            except BaseException:
                await self.close()
                raise


class MediaSender:
    label = "YouTube player"
    action_types = ("computer.media.play", "computer.media.stop")
    def __init__(self, player):
        self.player = player
    def is_connected(self):
        return bool(get_setting("computer_enabled") and get_setting("browser_enabled"))
    async def send(self, out):
        try:
            enabled()
            if out.action_type == "computer.media.stop":
                async with self.player.lock:
                    if not self.player.session or self.player.session != out.meta.get("media_session"):
                        return SendResult("failed", "The player changed since this card was created; nothing was stopped.")
                    await self.player.close()
                return SendResult("sent", "Stopped Junior's YouTube player.")
            return SendResult("sent", await self.player.play(json.loads(out.text)))
        except VerificationRequired as error:
            return SendResult("unclear", str(error))
        except Exception:
            return SendResult("failed", "Couldn't stop Junior's YouTube player." if out.action_type == "computer.media.stop"
                              else "YouTube couldn't confirm playback. No automatic retry was made.")
