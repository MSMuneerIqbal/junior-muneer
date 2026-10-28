"""WhatsApp (P8-04): talk to Junior Muneer on WhatsApp - text, voice notes, and your OK on drafts.

    GET  /api/whatsapp/webhook   Meta checks the webhook address (your verify token)
    POST /api/whatsapp/webhook   messages from WhatsApp (signed by Meta; the signature is checked)

Only your own number is answered: anything else is ignored and logged. Messages go into a
WhatsApp chat in the same history as the dashboard (🟢 in the chat list). Answers come back as
text; drafts come as their own message with buttons (Posted ✓ or Approve, and Reject).
Meta lets a business reply freely within 24 hours of your last message, which is how this works.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from junior.audit import audit
from junior.config import get_settings
from junior.db import Conversation, WhatsAppInbound, session_scope
from junior.db.models import utcnow
from junior.timeutil import zone

log = logging.getLogger(__name__)
router = APIRouter()
GRAPH = "https://graph.facebook.com"
MAX_CHARS = 3900  # WhatsApp allows 4096 per message
DRAFT_PREVIEW = 900  # a draft's text in its approval message (buttons can't carry more than 1024)
CARRY_MESSAGES = 8  # a short previous chat is carried over as its last few messages

# Tests set this; FAKE_AI with WHATSAPP_TOKEN=fake uses a pretend WhatsApp (sent messages kept in FAKE_SENT).
TRANSPORT: httpx.AsyncBaseTransport | None = None
FAKE_SENT: list[dict] = []

RESUME_MINUTES = 30  # after a restart, messages left unanswered this recently are answered; older ones aren't
MAX_ATTEMPTS = 2  # a message that stopped the app twice isn't tried again
_lock = asyncio.Lock()  # one message at a time, so answers keep their order
_jobs: set[asyncio.Task] = set()


def configured() -> bool:
    s = get_settings()
    return bool(s.whatsapp_token and s.whatsapp_phone_number_id and s.whatsapp_owner_number and s.meta_app_secret)


def digits(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def verify_signature(body: bytes, header: str, secret: str) -> bool:
    """Meta signs every webhook call with your app secret (X-Hub-Signature-256: sha256=<hex>)."""
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


_VOICE = r"(voice|audio|awaz|aawaz|awaaz|آواز|وائس)"
# Asking for a spoken answer ("send me voice", "voice mein batao", "آواز میں بتاؤ"), not just mentioning the word.
_ASK_VOICE = re.compile(
    rf"\b(send|give|reply|answer|speak|tell|say)\b[^.?!\n]{{0,20}}\b(in |by |as |a |with )?{_VOICE}"
    rf"|{_VOICE}\s*(note|message|msg|reply)?\s*(mein|me|main|men|mai|میں)\b"
    rf"|{_VOICE}\s*(note|message|msg|reply)?\s*(bhejo|bhej|do|de|dein|dena|please|pls|plz|بھیجو|دو|دیں)"
    rf"|\b(bol|bool) ?(kar|ke)\b|بول کر|سناؤ|سنا دو|\bsunao\b|\bsuna do\b",
    re.IGNORECASE,
)


def wants_voice(text: str) -> bool:
    """Did you ask, in a typed message, for the answer as a voice note?"""
    return bool(_ASK_VOICE.search(text or ""))


def to_whatsapp(markdown: str) -> str:
    """Chat markdown -> WhatsApp's own: *bold*, _italic_, links written out."""
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", markdown, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"_\1_", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text)
    return text.strip()


def split(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Long answers in several messages, cut between paragraphs or lines."""
    parts, rest = [], text.strip()
    while len(rest) > limit:
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return [p for p in [*parts, rest] if p]


class WhatsApp:
    """The WhatsApp Cloud API (Meta's Graph API) for one business phone number."""

    def __init__(self, token: str, phone_id: str, version: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.token, self.phone_id, self.version, self.transport = token, phone_id, version, transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{GRAPH}/{self.version}/", timeout=30, transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    async def _send(self, to: str, payload: dict) -> None:
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": digits(to), **payload}
        async with self._client() as c:
            r = await c.post(f"{self.phone_id}/messages", json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"WhatsApp said no ({r.status_code}): {r.text[:200]}")
        audit("action", "whatsapp_sent", detail={"type": payload.get("type")})

    async def send_text(self, to: str, text: str) -> None:
        for part in split(to_whatsapp(text)):
            await self._send(to, {"type": "text", "text": {"preview_url": False, "body": part}})

    async def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> None:
        await self._send(to, {
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}} for i, t in buttons[:3]]},
            },
        })

    async def _upload(self, data: bytes, filename: str, mime: str) -> str:
        async with self._client() as c:
            r = await c.post(
                f"{self.phone_id}/media",
                data={"messaging_product": "whatsapp", "type": mime},
                files={"file": (filename, data, mime)},
            )
        if r.status_code >= 400:
            raise RuntimeError(f"WhatsApp didn't take the file ({r.status_code}): {r.text[:200]}")
        return r.json()["id"]

    async def send_audio(self, to: str, data: bytes, mime: str = "audio/mpeg") -> None:
        """A spoken answer: upload the file to WhatsApp, then send it."""
        await self._send(to, {"type": "audio", "audio": {"id": await self._upload(data, "answer.mp3", mime)}})

    async def send_document(self, to: str, data: bytes, filename: str, mime: str, caption: str = "") -> None:
        """A file (a Word document, a PDF...): upload it, then send it with its name."""
        document = {"id": await self._upload(data, filename, mime), "filename": filename}
        if caption:
            document["caption"] = caption[:1024]
        await self._send(to, {"type": "document", "document": document})

    async def download(self, media_id: str) -> tuple[bytes, str]:
        """A voice note, document or photo you sent: its address first, then the file (both need the token)."""
        async with self._client() as c:
            meta = await c.get(media_id)
            if meta.status_code >= 400:
                raise RuntimeError(f"Couldn't get the file from WhatsApp ({meta.status_code})")
            info = meta.json()
            r = await c.get(info["url"])
            if r.status_code >= 400:
                raise RuntimeError(f"Couldn't download the file from WhatsApp ({r.status_code})")
        return r.content, info.get("mime_type", "audio/ogg")

    async def check(self) -> str:
        try:
            async with self._client() as c:
                r = await c.get(self.phone_id, params={"fields": "display_phone_number,verified_name"})
        except httpx.HTTPError:
            return "Couldn't reach WhatsApp. Check the internet connection and try again."
        if r.status_code == 401:
            return "The WhatsApp token doesn't work (expired?). Make a new one and run connect.bat whatsapp again."
        if r.status_code >= 400:
            return f"WhatsApp said no ({r.status_code}). Check the phone number ID."
        info = r.json()
        return f"Connected: {info.get('verified_name', 'your business')} ({info.get('display_phone_number', '?')})."


def _fake_whatsapp() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media.fake"})
        if request.method == "POST":
            FAKE_SENT.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.fake"}]})
        return httpx.Response(200, json={"verified_name": "Junior Muneer (fake)", "display_phone_number": "+1 555 0100"})

    return httpx.MockTransport(handler)


def client() -> WhatsApp:
    s = get_settings()
    transport = TRANSPORT
    if transport is None and s.fake_ai and s.whatsapp_token == "fake":
        transport = _fake_whatsapp()
    return WhatsApp(s.whatsapp_token, s.whatsapp_phone_number_id, s.meta_graph_version, transport)


# ---- your WhatsApp chat ----------------------------------------------------------------


def carried_summary(previous: Conversation) -> str:
    """What the new chat should know of the previous one: its running summary (long chats have one),
    or its last few messages (short chats). No AI cost: both are already there."""
    from junior.db import Message

    if previous.summary:
        return f"Earlier WhatsApp chat ({previous.title}), summarized:\n{previous.summary}"
    with session_scope() as s:
        recent = s.scalars(
            select(Message)
            .where(Message.conversation_id == previous.id, Message.source.in_(("user", "assistant")))
            .order_by(Message.id.desc())
            .limit(CARRY_MESSAGES)
        ).all()
        lines = [f"{'You' if m.role == 'user' else 'Junior Muneer'}: {' '.join(m.content.split())[:300]}" for m in reversed(recent)]
    return f"Earlier WhatsApp chat ({previous.title}), last messages:\n" + "\n".join(lines) if lines else ""


def whatsapp_chat(now: datetime | None = None) -> int:
    """The current WhatsApp chat, or a new one after your quiet time (Settings: 6, 12 or 24 hours, or every
    message). A new chat can start with a summary of the previous one, so the thread isn't lost."""
    from junior.settings_store import all_settings

    settings = all_settings()
    hours = int(settings.get("whatsapp_session_hours", 12))
    now = now or utcnow()
    with session_scope() as s:
        convo = s.scalars(
            select(Conversation).where(Conversation.kind == "whatsapp").order_by(Conversation.updated_at.desc())
        ).first()
        updated = None
        if convo is not None:
            updated = convo.updated_at if convo.updated_at.tzinfo else convo.updated_at.replace(tzinfo=UTC)
        if convo is not None and hours > 0 and now - updated <= timedelta(hours=hours):
            return convo.id
        previous = convo
        local = now.astimezone(zone(settings["timezone"]))
        title = f"WhatsApp · {local.strftime('%a %d %b')}" + (f", {local.strftime('%H:%M')}" if hours == 0 else "")
        convo = Conversation(title=title, kind="whatsapp")
        if previous is not None and settings.get("whatsapp_carry_summary", True):
            convo.summary = carried_summary(previous) or None
        s.add(convo)
        s.flush()
        return convo.id


def is_whatsapp_chat(conversation_id: int | None) -> bool:
    if conversation_id is None:
        return False
    with session_scope() as s:
        convo = s.get(Conversation, conversation_id)
        return bool(convo and convo.kind == "whatsapp")


def _buttons(item: dict) -> list[tuple[str, str]]:
    first = ("approve", "Approve") if item["kind"] == "api" else ("posted", "Posted ✓")
    return [(f"{first[0]}:{item['id']}", first[1]), (f"reject:{item['id']}", "Reject")]


async def send_drafts(to: str, items: list[dict]) -> None:
    for item in items:
        text = item["text"] if len(item["text"]) <= DRAFT_PREVIEW else item["text"][:DRAFT_PREVIEW] + "…"
        score = f" · {item['meta']['score']}/10" if item.get("meta", {}).get("score") is not None else ""
        body = f"{item['platform_label']} {item['item_type']}{score}\n\n{text}"
        if item.get("platform") == "email":  # who it goes to, and that Approve sends it
            attached = f"\n\nAttached: {item['meta']['attachment']}" if item.get("meta", {}).get("attachment") else ""
            body = f"Email {item['title']}\n\n{text}{attached}\n\nApprove sends it from your Gmail."
        if item.get("platform") == "computer":
            if item.get("status") == "posted":  # your rule was Auto: already done, nothing to tap
                if item.get("meta", {}).get("op") == "browser":
                    continue  # The final reply summarizes an automatic multi-step browser job.
                await client().send_text(to, f"Done on your PC: {pc_result(item)}")
                continue
            body = pc_card(item, text)
        await client().send_buttons(to, body, _buttons(item))


def pc_card(item: dict, text: str) -> str:
    """A PC action as a WhatsApp message: what it does, the change or the command, and what Approve does."""
    meta = item.get("meta", {})
    kind = item.get("item_type")
    if kind == "command":
        return f"Your PC: run this command in {meta.get('path', '')}\n\n{text}\n\nApprove runs it; the output comes back here."
    if kind == "file" and meta.get("diff"):
        diff = meta["diff"] if len(meta["diff"]) <= DRAFT_PREVIEW else meta["diff"][:DRAFT_PREVIEW] + "…"
        return f"Your PC: {item['title']}\n\n{diff}\n\nApprove makes the change (the old version goes to the Recycle Bin)."
    if kind == "file":
        return f"Your PC: {item['title']}\n\n{text}\n\nApprove creates it."
    return f"Your PC: {text}\n\nApprove does it."


def pc_result(item: dict) -> str:
    result = str(item.get("meta", {}).get("result", "")) or item.get("title", "")
    return result if len(result) <= MAX_CHARS - 200 else result[: MAX_CHARS - 200] + "\n… (more on the dashboard)"


async def answer(app: Any, text: str, audio_id: str | None = None, audio_seconds: float | None = None) -> None:
    """Run a normal chat turn in your WhatsApp chat and send the answer (and any drafts) back.
    Voice note in: voice note out. Text in: text out, unless you asked for voice ("voice mein batao").
    If speech fails, the text goes."""
    owner = get_settings().whatsapp_owner_number
    convo = whatsapp_chat()
    drafts, reply, problem, message_id = [], "", "", None
    from junior.permissions import ACTION_CHANNEL
    channel_token = ACTION_CHANNEL.set("whatsapp")
    try:
        async for event in app.state.chat.reply(convo, text, audio_id, audio_seconds):
            if event["type"] == "approval":
                drafts.append(event["item"])
            elif event["type"] == "done":
                reply, message_id = event["text"], event["message_id"]
            elif event["type"] == "error":
                problem = event["message"]
    finally:
        ACTION_CHANNEL.reset(channel_token)
    spoken = False
    if (audio_id or wants_voice(text)) and reply and message_id is not None:
        try:
            from junior.voice import speak_message

            mp3 = await speak_message(app.state.voice, message_id)
            if mp3:
                await client().send_audio(owner, mp3)
                spoken = True
        except Exception as e:  # no voice: the text still goes
            log.warning("WhatsApp voice reply failed, sending text: %s: %s", type(e).__name__, e)
    if not spoken:
        await client().send_text(owner, reply or problem or "I couldn't answer that just now. Please try again.")
    await send_drafts(owner, drafts)
    try:
        from junior.inbox import deliver_waiting

        await deliver_waiting()  # email alerts that waited for WhatsApp's 24-hour window
    except Exception:
        log.exception("Couldn't deliver waiting email alerts")


async def on_button(button_id: str, app: Any = None) -> str:
    """Your tap on a draft's button -> the same action as on the dashboard (Approve also sends it, like there)."""
    from junior.approvals import ApprovalError, approve_item, mark_posted, reject_item

    action, _, number = button_id.partition(":")
    actions = {"posted": (mark_posted, "Marked as posted"), "approve": (approve_item, "Approved"), "reject": (reject_item, "Rejected")}
    if action not in actions or not number.isdigit():
        return "I didn't understand that button."
    fn, done = actions[action]
    try:
        item = fn(int(number))
    except LookupError:
        return "That draft isn't there anymore."
    except ApprovalError as e:
        return f"Couldn't do that: {e}"
    senders = getattr(getattr(app, "state", None), "senders", None)
    if action == "approve" and senders is not None and item.action_type and senders.for_action(item.action_type):
        from junior.senders.dispatch import SendError, send_item

        try:
            item = await send_item(item.id, senders)
        except SendError as e:
            return f"Approved, but not sent: {e}"
        if item.platform == "computer":
            if item.status == "posted":
                return f"Done on your PC: {pc_result(item.model_dump(mode='json'))}"
            return f"Approved, but it didn't run: {item.meta.get('last_error', 'check the dashboard')}"
        if item.status == "posted":
            if item.item_type == "file_transfer":
                result = str(item.meta.get("result", "Done: " + item.title))
                link = str(item.meta.get("post_url", ""))
                return result + ("\n" + link if link and link not in result else "")
            return f"Sent: {item.title}."
        return f"Approved, but it didn't go out: {item.meta.get('last_error', 'check the dashboard')}."
    return f"{done}: {item.platform_label} {item.item_type}."


async def received_file(wa: "WhatsApp", msg: dict) -> str:
    """A document or photo you sent: keep it (junior/files.py) and make your message from its tag and caption."""
    from junior.files import save_received

    kind = msg["type"]
    media = msg.get(kind, {})
    data, mime = await wa.download(media["id"])
    if kind == "image":
        ending = {"image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
        filename = f"photo {utcnow().astimezone(zone(get_settings_tz())).strftime('%Y-%m-%d %H%M')}{ending}"
    else:
        filename = media.get("filename") or "document"
    _number, label = save_received(data, filename, media.get("mime_type") or mime, "whatsapp")
    caption = (media.get("caption") or "").strip()
    return f"{label}\n{caption}" if caption else f"{label}\n(I sent this file without saying what to do with it.)"


def get_settings_tz() -> str:
    from junior.settings_store import get_setting

    return get_setting("timezone")


async def handle(app: Any, msg: dict) -> None:
    """One message from WhatsApp (already checked: signed by Meta)."""
    s = get_settings()
    sender = msg.get("from", "")
    if digits(sender) != digits(s.whatsapp_owner_number):
        audit("action", "whatsapp_ignored", result="refused", detail={"from_last4": digits(sender)[-4:], "type": msg.get("type")})
        return
    kind = msg.get("type")
    wa = client()
    async with _lock:
        try:
            if kind == "text":
                await answer(app, msg.get("text", {}).get("body", "").strip())
            elif kind == "audio":
                from junior.voice import transcribe_bytes

                data, mime = await wa.download(msg["audio"]["id"])
                heard = await transcribe_bytes(app.state.voice, data, mime)
                if not heard["text"]:
                    await wa.send_text(sender, "I couldn't hear that clearly. Could you say it again, or type it?")
                    return
                await answer(app, heard["text"], heard["audio_id"], heard["seconds"])
            elif kind in ("document", "image"):
                await answer(app, await received_file(wa, msg))
            elif kind == "interactive" and msg.get("interactive", {}).get("type") == "button_reply":
                await wa.send_text(sender, await on_button(msg["interactive"]["button_reply"]["id"], app))
            else:
                await wa.send_text(sender, "I can take text, voice notes, documents and photos here.")
        except ValueError as e:  # a file that's empty or too big
            await wa.send_text(sender, f"I couldn't take that file: {e}")
        except HTTPException as e:  # a voice note that couldn't be transcribed
            await wa.send_text(sender, f"I couldn't use that voice note: {e.detail}")
        except Exception as e:
            log.exception("WhatsApp message failed")
            audit("action", "whatsapp_failed", result="error", detail={"error": f"{type(e).__name__}: {e}"})
            try:
                await wa.send_text(sender, "Something went wrong on my side. Please try again in a minute.")
            except Exception:
                log.exception("Couldn't even send the error to WhatsApp")


async def post_to_whatsapp(conversation_id: int | None, text: str, *, file_ids: list[int] | None = None,
                           approval_ids: list[int] | None = None) -> None:
    """A background task finished in your WhatsApp chat: send its result there too."""
    if not configured() or not is_whatsapp_chat(conversation_id):
        return
    try:
        owner = get_settings().whatsapp_owner_number
        # A localhost dashboard download is not usable on their phone. Deliver the actual finished file.
        phone_text = re.sub(r"\[Download[^\]]*\]\(/api/files/\d+/download\)", "The finished file is attached below.", text)
        phone_text = re.sub(r"\[Open saved notes\]\(/notes\?id=\d+\)", "Saved in your Notes library in the dashboard.", phone_text)
        await client().send_text(owner, phone_text)
        if file_ids:
            from junior.files import received
            for number in file_ids:
                found = received(number)
                if found and found[0].source == "generated" and found[0].conversation_id == conversation_id:
                    row, data = found
                    await client().send_document(owner, data, row.filename, row.mime)
        if approval_ids:
            from junior.approvals import get_item
            cards = [get_item(i).model_dump(mode="json") for i in approval_ids]
            await send_drafts(owner, cards)
    except Exception:
        log.exception("Couldn't send a background result to WhatsApp")


async def mirror_to_whatsapp(conversation_id: int | None, question: str, reply: str, cards: list[dict]) -> None:
    """You wrote in your WhatsApp chat from the dashboard: the answer (and its cards) reaches your phone too,
    with your question on top so it makes sense there (P10-01)."""
    if not configured() or not is_whatsapp_chat(conversation_id) or not (reply or cards):
        return
    owner = get_settings().whatsapp_owner_number
    asked = " ".join(question.split())
    asked = asked if len(asked) <= 300 else asked[:300] + "…"
    try:
        if reply:
            await client().send_text(owner, f"_You, on the dashboard:_ {asked}\n\n{reply}")
        await send_drafts(owner, cards)
    except Exception:  # noqa: BLE001 - most often WhatsApp's 24-hour window; the dashboard has it anyway
        log.exception("Couldn't send the dashboard answer to WhatsApp")


def _new(msg: dict) -> bool:
    """Keep a message until it's answered. False if Meta already delivered it (it does that at times)."""
    from sqlalchemy.exc import IntegrityError

    message_id = msg.get("id", "")
    if not message_id:
        return False
    try:
        with session_scope() as s:
            s.add(WhatsAppInbound(wa_message_id=message_id, payload=msg))
    except IntegrityError:
        return False
    return True


async def _work(app: Any, msg: dict) -> None:
    """Answer one kept message, then mark it done (whatever happened, the reply or an error message went out)."""
    message_id = msg.get("id", "")
    with session_scope() as s:
        row = s.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wa_message_id == message_id))
        if row is not None:
            row.attempts += 1
    try:
        await handle(app, msg)
    finally:
        with session_scope() as s:
            row = s.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wa_message_id == message_id))
            if row is not None:
                row.status, row.finished_at = "done", utcnow()


def _start(app: Any, msg: dict) -> None:
    job = asyncio.create_task(_work(app, msg))
    _jobs.add(job)
    job.add_done_callback(_jobs.discard)


def resume_unanswered(app: Any) -> int:
    """At startup: answer the messages a restart cut off (recent ones, in order). Returns how many."""
    if not configured():
        return 0
    since = utcnow() - timedelta(minutes=RESUME_MINUTES)
    with session_scope() as s:
        rows = s.scalars(
            select(WhatsAppInbound).where(WhatsAppInbound.status == "pending").order_by(WhatsAppInbound.id)
        ).all()
        resume = []
        for row in rows:
            if row.created_at >= since and row.attempts < MAX_ATTEMPTS:
                resume.append(dict(row.payload))
            else:
                row.status, row.finished_at = "expired", utcnow()
                audit("action", "whatsapp_not_resumed", result="skipped",
                      detail={"attempts": row.attempts, "type": row.payload.get("type")})
    for msg in resume:
        log.info("Answering a WhatsApp message a restart cut off")
        _start(app, msg)
    return len(resume)


# ---- API --------------------------------------------------------------------


@router.get("/api/whatsapp/webhook")
def verify_webhook(request: Request) -> PlainTextResponse:
    q = request.query_params
    token = get_settings().whatsapp_verify_token
    if q.get("hub.mode") == "subscribe" and token and hmac.compare_digest(q.get("hub.verify_token", ""), token):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Wrong verify token.")


@router.post("/api/whatsapp/webhook")
async def receive(request: Request) -> dict:
    if not configured():
        raise HTTPException(404, "WhatsApp isn't connected.")
    body = await request.body()
    if not verify_signature(body, request.headers.get("x-hub-signature-256", ""), get_settings().meta_app_secret):
        audit("action", "whatsapp_bad_signature", result="refused")
        raise HTTPException(403, "Bad signature.")
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                if _new(msg):
                    _start(request.app, msg)  # answer Meta at once; work after
    return {"ok": True}
