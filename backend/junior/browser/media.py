"""A single, user-requested YouTube playback action with its own visible temporary player."""

import asyncio
import json
import re
import socket
import time
import unicodedata
from difflib import SequenceMatcher
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
PLAY = re.compile(r"\b(play|paly|bajao|baja|chalao|chalo|chala|lagao|lgao|lagado|laga|lga|sunao)\b|پلے|چلاؤ|چلا|بجاؤ|بجائیں|لگاؤ|لگائیں|سناؤ|سنائیں", re.I)
SONG = re.compile(r"\b(song|music|gaana|gana|geet|track|youtube)\b|گانا|گانے|سونگ|سانگ|گیت|نغمہ|نغمے|موسیقی|یوٹیوب", re.I)
STOP = re.compile(r"\b(stop|close|quit|band|rok|roko)\b|بند|روک", re.I)
CHANGE = re.compile(r"\b(change|next|skip|badal|badlo|badal[o]?)\b|بدل|اگلا", re.I)
NEGATED = re.compile(r"\b(?:do\s+not|don['’]?t|dnt|never|not|mat|nahin|nahi)\b.{0,35}\b(?:play|paly|bajao|baja|chalao|chalo|chala|lagao|lgao|lagado|laga|lga|sunao)\b|(?:نہ|مت).{0,35}(?:پلے|چلا|بجا|لگا|سنا)|پلے\s+(?:نہ|مت)\s*کر", re.I)
HOW_TO = re.compile(r"\b(?:how\s+(?:do|can|to)|why\s+(?:does|do|is)|kaise|kaisay|kyun)\b", re.I)
ROLE_PLAY = re.compile(r"\bplay\s+(?:the\s+)?role\b", re.I)
DISCUSSION = re.compile(r"^(?:please\s+)?(?:translate|summari[sz]e|explain|write|draft|describe|tell\s+me\s+about|what\s+is|where\b)\b", re.I)
PERSONAL_BROWSER = re.compile(r"\b(?:signed[ -]?in|logged[ -]?in|personal browser|my browser|my chrome)\b", re.I)
EXTRA_TASK = re.compile(r"\b(?:and|then|aur|phir)\b.{0,80}\b(?:send|email|write|create|save|download|upload|delete|message|search)\b", re.I)
STOPWORDS = {"play", "paly", "song", "music", "youtube", "kro", "karo", "krdo", "kr", "do", "yr", "yaar", "bhai", "wala", "wali", "ka", "ki", "ko", "on", "to", "the", "please", "bajao", "baja", "chalao", "chalo", "chala", "lagao", "laga", "lagado", "lga", "sunao", "gana", "gaana", "geet", "track", "change", "ab", "pc", "mn", "mein", "یار", "ایک", "سونگ", "تو", "چلا", "دو", "یوٹیوب", "پہ"}
STOPWORDS.update({"پلے", "کرو", "کریں", "کر", "کا", "کی", "کے", "جس", "نام", "ہے", "ہیں", "یہ", "کو", "گانا", "گانے", "سانگ", "گیت", "نغمہ", "نغمے", "مجھے", "میرا", "والی", "والا", "والے", "سناؤ", "سنائیں", "بجاؤ", "بجائیں", "لگاؤ", "لگائیں", "چلائیں"})
STOPWORDS.update({"my", "personal", "signed", "logged", "in", "browser", "chrome"})


class VerificationRequired(RuntimeError):
    """The site asked the owner to complete its verification in the visible player."""


def is_request(text: str) -> bool:
    text = text or ""
    short_title = (re.match(r"^\s*(?:song|gaana|gana|سونگ|گانا)\s+", text, re.I)
                   and not re.search(r"\b(?:lyrics|meaning|translation|history|about|who|what|where|how|why)\b", text, re.I)
                   and len(terms(text)) >= 2 and "?" not in text)
    return bool((PLAY.search(text) or short_title) and SONG.search(text) and not NEGATED.search(text)
                and not HOW_TO.search(text) and not ROLE_PLAY.search(text) and not DISCUSSION.search(text.strip())
                and not EXTRA_TASK.search(text))


def is_stop_request(text: str) -> bool:
    return bool(STOP.search(text or "") and SONG.search(text or "") and not DISCUSSION.search(text.strip())
                and not re.search(r"\b(?:do\s+not|don['’]?t|never|mat|nahi|nahin)\b.{0,25}\b(?:stop|close|band|rok|roko)\b|(?:نہ|مت).{0,25}(?:بند|روک)", text, re.I))


def is_change_request(text: str) -> bool:
    text = (text or "").strip()
    return bool(CHANGE.search(text) and not DISCUSSION.search(text) and not HOW_TO.search(text)
                and not EXTRA_TASK.search(text)
                and not re.search(r"\b(?:do\s+not|don't|never|mat|nahi|nahin)\b.{0,25}\b(?:change|skip|badal|badlo)\b|(?:نہ|مت).{0,25}بدل", text, re.I)
                and (re.fullmatch(r"(?:please\s+)?(?:change\s+it|change|next|skip|badal\s+do|badlo|(?:change|next|skip)\s+(?:the\s+)?(?:song|music|track)|(?:song|music|gana|gaana)\s+(?:change|badal|badlo)(?:\s+(?:kro|karo|do|krdo))?)\s*[.!]?", text, re.I) or re.fullmatch(r"(?:گانا|گانے)\s+(?:بدل\s+دو|بدلو)|اگلا\s+گانا", text)))


def is_continue(text: str) -> bool:
    return bool(re.fullmatch(r"(?:continue|conitnue|contine|cont|aage|ag[ae]y|جاری\s+رکھو|جاری\s+رکھیں)\s*[.!؟]?", (text or "").strip(), re.I))


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
                player = active_player()
                if player and player.conversation_id == context.conversation_id and player.problem:
                    return {"reply": player.problem}
                return {"reply": "That song was already started. Ask for it again if you want to replay it."}
            return {"reply": "The previous playback did not complete or needs checking. Check its card before trying again."}
        return {"text": source.content, "id": source.id}


def terms(text: str) -> list[str]:
    words = re.findall(r"[^\W_]+", text.casefold())
    return ["dont" if word == "dnt" else word for word in words if len(word) > 1 and word not in STOPWORDS]


# Consonant skeletons permit Urdu song/artist names to match common Roman spellings.
# This is intentionally approximate; several matching words are still required below.
URDU_CONSONANTS = dict(zip("بپتٹثجچحخدڈذرڑزژسشصضطظعغفقکگلمںنہھءئاوؤییے", [
    "b", "p", "t", "t", "s", "j", "c", "h", "k", "d", "d", "z", "r", "r", "z", "z",
    "s", "s", "s", "z", "t", "z", "", "g", "f", "k", "k", "g", "l", "m", "n", "n",
    "h", "h", "", "", "", "", "", "", "", ""] ))


def phonetic_word(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.casefold())
    mapped = "".join(URDU_CONSONANTS.get(char, char) for char in word if not unicodedata.combining(char))
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[^a-z]|[aeiouhwy]", "", mapped))


def word_matches(wanted: str, actual: str) -> bool:
    if actual == wanted or (len(wanted) >= 4 and (actual.startswith(wanted) or wanted.startswith(actual))):
        return True
    if not (any("\u0600" <= c <= "\u06ff" for c in wanted) and actual.isascii()):
        return False
    first, second = phonetic_word(wanted), phonetic_word(actual)
    return bool(len(first) >= 2 and len(second) >= 2 and
                (first == second or (min(len(first), len(second)) >= 3 and SequenceMatcher(None, first, second).ratio() >= 0.8)))


def matches_request(text: str, title: str) -> bool:
    wanted, actual = terms(text), terms(title)
    if not wanted:
        return False
    matches = sum(any(word_matches(w, a) for a in actual) for w in wanted)
    if "dont" in wanted and "don" in actual and "dont" not in actual:
        matches += 1  # YouTube commonly tokenizes “don't” as “don” and “t”.
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
            if item.action_type == "computer.media.change":
                return payload == {"next": True} and is_change_request(message.content) and bool(item.meta.get("media_session"))
            mode = bool(get_setting("signed_browser_media"))
            if item.meta.get("media_signed_browser", False) is not mode:
                return False
            if mode:
                bridge = signed_bridge()
                if not bridge or not bridge.connected or item.meta.get("media_bridge_generation") != bridge.generation:
                    return False
            return bool(set(payload) == {"video_id", "title"} and VIDEO_ID.fullmatch(payload["video_id"])
                        and (not PERSONAL_BROWSER.search(message.content) or mode)
                        and is_request(message.content) and matches_request(message.content, payload["title"]))
    except (ValueError, TypeError, KeyError):
        return False


async def prepare(context, text: str) -> str:
    from junior.computer.tools import queue_action
    try:
        enabled()
        if PERSONAL_BROWSER.search(text) and not get_setting("signed_browser_media"):
            raise BrowserRefused("Select My Chrome profile under Settings → Computer → YouTube browser, then connect the Chrome extension.")
        from junior.privacy import credential_present
        if len(text) > 300 or credential_present(text):
            raise BrowserRefused("Send just the song title and artist, without sensitive information.")
        if not is_request(text) or not context.user_message_ids:
            raise BrowserRefused("Ask for a song to play in your own message.")
        mode = bool(get_setting("signed_browser_media"))
        bridge = signed_bridge() if mode else None
        if mode and (not bridge or not bridge.connected):
            raise BrowserRefused("Connect the signed-in Chrome extension in Settings → Computer first.")
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
                                  {"op": "media_play", "media_user_message_id": source, "seconds": 60,
                                   "media_signed_browser": mode, "media_bridge_generation": bridge.generation if bridge else ""})
    except BrowserRefused as error:
        return f"NOT done: {error}"
    except (httpx.HTTPError, ValueError, RecursionError):
        return "NOT done: YouTube search is unavailable. Try again later."


def active_player():
    from junior.senders.registry import CURRENT
    sender = CURRENT.for_action("computer.media.stop")
    return sender.player if sender and sender.player.session else None


def signed_bridge():
    from junior.senders.registry import CURRENT
    sender = CURRENT.for_action("computer.media.play")
    return sender.player.signed_bridge if sender else None


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


async def prepare_change(context, text: str) -> str:
    from junior.computer.tools import queue_action
    try:
        enabled()
        player = active_player()
        if not player or player.conversation_id != context.conversation_id:
            return "NOT done: There is no active YouTube player from this chat to change."
        with session_scope() as session:
            source = session.scalar(select(Message.id).where(Message.id.in_(context.user_message_ids),
                                    Message.conversation_id == context.conversation_id, Message.source == "user",
                                    Message.content == text).order_by(Message.id.desc()).limit(1))
        if not source or not is_change_request(text):
            raise BrowserRefused("I couldn't verify the request to change the song.")
        return await queue_action(context, "computer.media.change", "media", json.dumps({"next": True}),
                                  "Play the next YouTube video", {"op": "media_change",
                                  "media_user_message_id": source, "media_session": player.session})
    except BrowserRefused as error:
        return f"NOT done: {error}"


class Player:
    def __init__(self, fake=False, signed_bridge=None):
        self.fake = fake
        self.signed_bridge = signed_bridge
        self.signed_session = False
        self.pw = self.browser = self.context = self.page = self.watch = None
        self.lock = asyncio.Lock()
        self.video_id = ""
        self.session = ""
        self.conversation_id = None
        self.changing = False
        self.problem = ""

    async def close(self):
        watch, self.watch = self.watch, None
        if watch and watch != asyncio.current_task():
            watch.cancel()
            await asyncio.gather(watch, return_exceptions=True)
        if self.signed_session:
            self.signed_session = False
            if self.signed_bridge and self.signed_bridge.connected:
                try:
                    await self.signed_bridge.command("media_stop", {}, timeout=5)
                except (ConnectionError, TimeoutError, ValueError):
                    pass
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
        self.conversation_id = None
        self.problem = ""

    async def _watch_signed(self):
        deadline = time.monotonic() + 900
        try:
            while self.session and time.monotonic() < deadline:
                enabled()
                if not get_setting("signed_browser_media") or rule_for("computer.media.play") == "deny" or rule_for("computer.browser.input") == "deny":
                    break
                if not self.signed_bridge or not self.signed_bridge.connected:
                    self.problem = "The signed-in Chrome connection was lost. Check the YouTube tab before trying again."
                    return
                try:
                    state = await self.signed_bridge.command("media_status", {}, timeout=5)
                    if isinstance(state, dict) and state.get("state") == "error":
                        self.problem = "YouTube stopped playback with a player error. Check the Chrome tab before trying again."
                    elif isinstance(state, dict) and state.get("state") == "playing":
                        self.problem = ""
                    elif isinstance(state, dict) and state.get("outcome") == "failed":
                        self.problem = "Junior's Chrome tab was closed or changed. Check it before trying again."
                except (ConnectionError, TimeoutError):
                    self.problem = "Could not check the Chrome player. Check the tab before trying again."
                await asyncio.sleep(5)
        except (BrowserRefused, asyncio.CancelledError):
            pass
        finally:
            if not self.problem or (self.signed_bridge and self.signed_bridge.connected):
                await self.close()

    async def stop_owned(self):
        if self.signed_session:
            if not self.signed_bridge or not self.signed_bridge.connected:
                raise RuntimeError("The Chrome connection is lost; check the YouTube tab before trying again.")
            result = await self.signed_bridge.command("media_stop", {}, timeout=8)
            if not isinstance(result, dict) or result.get("outcome") != "sent":
                raise RuntimeError("Could not confirm that Junior's Chrome tab was closed.")
            self.signed_session = False
        await self.close()

    async def check_playback(self):
        """Detect a visible player failure without reading account or page contents."""
        if not self.page or self.changing:
            return
        try:
            state = await self.page.evaluate("""() => {
                const v = document.querySelector('video');
                const e = document.querySelector('.ytp-error-content-wrap');
                return { error: !!(v && v.error) || !!(e && e.offsetParent !== null),
                         playing: !!(v && !v.paused && v.currentTime > 1) };
            }""")
            if state.get("error"):
                self.problem = "YouTube stopped playback with a player error. The player is still open; check it before trying again."
            elif state.get("playing"):
                self.problem = ""
        except Exception:
            # The page may close or navigate while it is being observed.
            pass

    async def _watch(self):
        deadline = time.monotonic() + 900
        try:
            while self.page and not self.page.is_closed() and time.monotonic() < deadline:
                enabled()
                if rule_for("computer.media.play") == "deny" or rule_for("computer.browser.input") == "deny":
                    break
                url = urlsplit(self.page.url)
                if not self.changing and url.path == "/watch" and parse_qs(url.query).get("v", [""])[0] != self.video_id:
                    break  # do not automatically play a different video
                await self.check_playback()
                await asyncio.sleep(1)
        except (BrowserRefused, asyncio.CancelledError):
            pass
        finally:
            await self.close()

    async def play(self, payload, *, expected_mode=None, expected_generation=None):
        async with self.lock:
            enabled()
            mode = bool(get_setting("signed_browser_media"))
            if expected_mode is not None and expected_mode is not mode:
                raise BrowserRefused("The selected YouTube browser changed. Request the song again.")
            if mode and expected_generation is not None and (not self.signed_bridge or not self.signed_bridge.connected or self.signed_bridge.generation != expected_generation):
                raise BrowserRefused("The Chrome connection changed. Request the song again.")
            await self.close()
            self.session = uuid4().hex
            if mode:
                if not self.signed_bridge or not self.signed_bridge.connected:
                    self.session = ""
                    raise BrowserRefused("Connect the signed-in Chrome extension in Settings → Computer first.")
                self.signed_session = True
                self.video_id = payload["video_id"]
                task = asyncio.create_task(self.signed_bridge.command("media_play", {"video_id": self.video_id}, timeout=65))
                try:
                    while not task.done():
                        await asyncio.wait({task}, timeout=1)
                        enabled()
                        if not get_setting("signed_browser_media") or rule_for("computer.media.play") == "deny" or rule_for("computer.browser.input") == "deny":
                            raise BrowserRefused("The browser settings changed during playback.")
                    result = await task
                except (BrowserRefused, asyncio.CancelledError) as error:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    await self.close()
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    raise VerificationRequired("The player action was interrupted. Check Chrome before trying again.") from None
                except (ConnectionError, TimeoutError):
                    self.problem = "The Chrome tab may have opened, but playback could not be confirmed. Check it before retrying."
                    raise VerificationRequired(self.problem) from None
                self.watch = asyncio.create_task(self._watch_signed())
                if not isinstance(result, dict) or result.get("outcome") not in {"sent", "failed", "unclear"}:
                    raise VerificationRequired("Chrome returned an unclear playback result. Check the tab before retrying.")
                if result["outcome"] == "failed":
                    raise BrowserRefused("Chrome could not open Junior's YouTube tab.")
                if result["outcome"] == "unclear":
                    self.problem = "YouTube opened in Chrome, but playback could not be confirmed. Check the tab before retrying."
                    raise VerificationRequired(self.problem)
                return f"YouTube is playing in your Chrome tab: {payload['title']}."
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

    async def next(self):
        if self.signed_session:
            if not self.signed_bridge or not self.signed_bridge.connected:
                raise BrowserRefused("The signed-in Chrome extension is disconnected.")
            self.session = uuid4().hex
            result = await self.signed_bridge.command("media_next", {}, timeout=65)
            if not isinstance(result, dict) or result.get("outcome") != "sent":
                raise RuntimeError("The next video could not be confirmed in Chrome.")
            self.problem = ""
            return "Changed to the next YouTube video in your Chrome tab."
        if self.fake:
            self.session = uuid4().hex
            return "Simulated changing to the next song."
        if not self.page or self.page.is_closed():
            raise BrowserRefused("The YouTube player is no longer open.")
        href = await self.page.locator("a.ytp-next-button").first.get_attribute("href")
        from urllib.parse import urljoin
        target = urlsplit(urljoin("https://www.youtube.com", href or ""))
        ident = parse_qs(target.query).get("v", [""])[0]
        if target.scheme != "https" or target.hostname != "www.youtube.com" or target.path != "/watch" or not VIDEO_ID.fullmatch(ident) or ident == self.video_id:
            raise BrowserRefused("YouTube did not provide a usable next video.")
        self.changing = True
        try:
            # Invalidate other cards before navigation, including if its outcome is uncertain.
            self.session = uuid4().hex
            await self.page.goto("https://www.youtube.com/watch?v=" + ident, wait_until="commit", timeout=30000)
            self.video_id = ident
            await self.page.wait_for_function("""() => { const v = document.querySelector('video');
                return v && !v.paused && !v.muted && v.volume > 0 && v.currentTime > 1; }""", timeout=30000)
            return "Changed to the next YouTube video. An ad may play first."
        finally:
            self.changing = False


class MediaSender:
    label = "YouTube player"
    action_types = ("computer.media.play", "computer.media.stop", "computer.media.change")
    def __init__(self, player):
        self.player = player
    def is_connected(self):
        return bool(get_setting("computer_enabled") and get_setting("browser_enabled"))
    async def send(self, out):
        try:
            enabled()
            if out.action_type == "computer.media.change":
                async with self.player.lock:
                    if not self.player.session or self.player.session != out.meta.get("media_session"):
                        return SendResult("failed", "The player changed since this card was created; nothing was changed.")
                    try:
                        return SendResult("sent", await self.player.next())
                    except BrowserRefused as error:
                        return SendResult("failed", str(error))
                    except Exception:
                        return SendResult("unclear", "The song change could not be confirmed. Check the player before trying again.")
            if out.action_type == "computer.media.stop":
                async with self.player.lock:
                    if not self.player.session or self.player.session != out.meta.get("media_session"):
                        return SendResult("failed", "The player changed since this card was created; nothing was stopped.")
                    await self.player.stop_owned()
                return SendResult("sent", "Stopped Junior's YouTube player.")
            result = await self.player.play(json.loads(out.text), expected_mode=out.meta.get("media_signed_browser", False),
                                            expected_generation=out.meta.get("media_bridge_generation") or None)
            with session_scope() as session:
                source = session.get(Message, out.meta.get("media_user_message_id"))
                self.player.conversation_id = source.conversation_id if source and source.source == "user" else None
            return SendResult("sent", result)
        except VerificationRequired as error:
            return SendResult("unclear", str(error))
        except BrowserRefused as error:
            return SendResult("failed", str(error))
        except RuntimeError as error:
            return SendResult("unclear", str(error))
        except (ConnectionError, TimeoutError):
            return SendResult("unclear", "The browser connection was interrupted. Check the tab before trying again.")
        except Exception:
            return SendResult("failed", "Couldn't stop Junior's YouTube player." if out.action_type == "computer.media.stop"
                              else "YouTube couldn't confirm playback. No automatic retry was made.")
