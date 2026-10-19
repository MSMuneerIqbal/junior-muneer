"""Voice messages: speech-to-text for your recordings, text-to-speech for his answers.

    POST /api/voice/transcribe   upload a recording -> {audio_id, text, languages, seconds}
    GET  /api/voice/speak/{message_id}.mp3   one of his answers, read aloud (streams)
    GET  /api/audio/{audio_id}   play a saved recording or spoken answer

Recordings and spoken answers are saved in data/uploads/audio.
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from junior.agent.builder import NoApiKeyError
from junior.ai_client import ai_client
from junior.audit import audit
from junior.config import get_settings
from junior.costs import BudgetExceeded, budget_left
from junior.db import Message, Usage, session_scope
from junior.models import get_router
from junior.settings_store import ACCENTS, TTS_VOICES, all_settings, get_setting

log = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # OpenAI's limit for one file
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}
AUDIO_NAME = re.compile(r"^[0-9a-f]{32}\.(webm|ogg|m4a|mp3|wav)$")
MEDIA_TYPES = {"webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav"}

# Helps the speech-to-text with names and mixed languages.
# Spoken Urdu and Hindi sound alike, so the hint asks for Urdu script. If Hindi
# (Devanagari) script still comes back, we transcribe again with the language set
# to Urdu. The hint has no example sentences: on breathing or background noise the
# model tends to write out its hint, so example words came back as fake messages.
TRANSCRIBE_PROMPT = (
    "The speaker is {name}, from Pakistan, talking to their AI assistant Junior Muneer. "
    "Write down exactly what they say, in the language they say it; never translate. "
    "Write Urdu in Urdu script (not Hindi/Devanagari, not Roman Urdu) and English in English. "
    "If there is no speech (only breathing, coughs or background noise), write nothing."
)
# Average log-probability of the transcript's words. Measured: whole sentences score
# about -0.2 or better; short real words in a live call can score -1.1 ("Hello");
# text made up from breathing or background noise mostly scores -2.2 to -4.1.
NOISE_LOGPROB = -2.0


def average_logprob(logprobs) -> float | None:
    values = [lp.get("logprob") if isinstance(lp, dict) else getattr(lp, "logprob", None)
              for lp in (logprobs or [])]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def is_noise(text: str, logprobs) -> bool:
    """True for an empty transcript, or one the model itself wasn't sure about."""
    if not text.strip(" .،۔?!؟"):
        return True
    avg = average_logprob(logprobs)
    return avg is not None and avg < NOISE_LOGPROB
DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def audio_dir() -> Path:
    path = get_settings().data_path / "uploads" / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_path(audio_id: str) -> Path | None:
    """The file for an audio id, or None if the id is invalid or missing."""
    if not AUDIO_NAME.match(audio_id or ""):
        return None
    path = audio_dir() / audio_id
    return path if path.exists() else None


@dataclass
class TranscriptResult:
    text: str
    languages: list[str]
    seconds: float | None  # from the API when it reports it
    logprobs: list | None = None
    model: str | None = None  # set when a backup model did the work (Gemini busy -> OpenAI)


class VoiceClient(Protocol):
    async def transcribe(
        self, path: Path, model: str, prompt: str, language: str | None = None
    ) -> TranscriptResult: ...

    def speak(
        self, text: str, model: str, voice: str, speed: float, instructions: str
    ) -> AsyncIterator[bytes]: ...


class OpenAIVoice:
    def __init__(self) -> None:
        key = get_settings().openai_api_key
        if not key:
            raise NoApiKeyError("No OpenAI API key yet. Paste it into backend/.env.")
        self.client = ai_client(key)

    async def transcribe(
        self, path: Path, model: str, prompt: str, language: str | None = None
    ) -> TranscriptResult:
        extra = {"language": language} if language else {}
        if "gpt-4o" in model:  # these report how sure they are of each word
            extra.update(response_format="json", include=["logprobs"])
        with path.open("rb") as f:
            result = await self.client.audio.transcriptions.create(
                model=model, file=f, prompt=prompt, **extra
            )
        usage = getattr(result, "usage", None)
        seconds = getattr(usage, "seconds", None) if usage is not None else None
        languages = [
            getattr(lang, "code", None) or str(lang)
            for lang in (getattr(result, "languages", None) or [])
        ]
        return TranscriptResult(
            text=result.text.strip(),
            languages=languages,
            seconds=seconds,
            logprobs=getattr(result, "logprobs", None),
        )

    async def speak(
        self, text: str, model: str, voice: str, speed: float, instructions: str
    ) -> AsyncIterator[bytes]:
        """Streams the MP3 as OpenAI makes it, so playback can start in ~2 seconds."""
        kwargs = {"instructions": instructions} if "tts-1" not in model else {}
        async with self.client.audio.speech.with_streaming_response.create(
            model=model, voice=voice, input=text, speed=speed, response_format="mp3", **kwargs
        ) as response:
            async for chunk in response.iter_bytes():
                yield chunk


GEMINI_SPEAK_CHARS = 1500  # Gemini's speech model makes one piece at a time: short pieces start playing sooner
GEMINI_TIMEOUT_SECONDS = 120
GEMINI_AUDIO_TOKENS_PER_SECOND = 25
GEMINI_READ_ALOUD = "Read the text below aloud, word for word. Don't add or say anything else."


def to_mp3(pcm: bytes, rate: int = 24000) -> bytes:
    """Gemini's raw 16-bit mono audio -> MP3 (the dashboard plays it; WhatsApp only takes real audio files)."""
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm) + encoder.flush())


class GeminiVoice:
    """Voice messages with Google Gemini (Settings → Voice → Engine): Gemini 2.5 Flash writes down what you said,
    Gemini's speech model reads his answers in the Gemini voice you picked. Needs GEMINI_API_KEY."""

    def __init__(self) -> None:
        key = get_settings().gemini_api_key
        if not key:
            raise NoApiKeyError(
                "Voice messages with Gemini need GEMINI_API_KEY in backend/.env (then a restart), "
                "or switch Settings → Voice → Engine back to OpenAI."
            )
        from google import genai

        self.client = genai.Client(api_key=key)

    async def transcribe(
        self, path: Path, model: str, prompt: str, language: str | None = None
    ) -> TranscriptResult:
        from google.genai import types

        ask = prompt + (" They are speaking Urdu: write it in Urdu script." if language == "ur" else "")
        ask += " Reply with only their words: no notes, no labels, no quotes."
        audio = types.Part.from_bytes(data=path.read_bytes(), mime_type=MEDIA_TYPES[path.suffix[1:]])
        result = await asyncio.wait_for(
            self.client.aio.models.generate_content(model=model, contents=[audio, ask]), GEMINI_TIMEOUT_SECONDS
        )
        usage = result.usage_metadata
        audio_tokens = sum(
            d.token_count or 0 for d in (getattr(usage, "prompt_tokens_details", None) or [])
            if "AUDIO" in str(d.modality).upper()
        )
        return TranscriptResult(
            text=(result.text or "").strip(),
            languages=[],
            seconds=audio_tokens / GEMINI_AUDIO_TOKENS_PER_SECOND if audio_tokens else None,
        )

    async def speak(
        self, text: str, model: str, voice: str, speed: float, instructions: str
    ) -> AsyncIterator[bytes]:
        """One MP3 piece per short part of the answer (Gemini can't change speed; `speed` is for OpenAI)."""
        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
            ),
        )
        for piece in chunks(text, GEMINI_SPEAK_CHARS):
            result = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=model, contents=f"{instructions} {GEMINI_READ_ALOUD}\n\n{piece}", config=config
                ),
                GEMINI_TIMEOUT_SECONDS,
            )
            parts = result.candidates[0].content.parts if result.candidates and result.candidates[0].content else []
            pcm = b"".join(p.inline_data.data for p in parts or [] if getattr(p, "inline_data", None))
            if pcm:
                yield to_mp3(pcm)


# Tests put a pretend Gemini voice here.
GEMINI_VOICE = None


def voice_engine() -> str:
    return get_setting("voice_engine") or "openai"


class GeminiThenOpenAI:
    """Gemini first; when Gemini is busy or down (it answers "503 high demand" at times), OpenAI does that one
    recording or answer, so a voice message never goes unanswered."""

    def __init__(self, gemini, openai_voice) -> None:
        self.gemini, self.openai_voice = gemini, openai_voice

    async def transcribe(
        self, path: Path, model: str, prompt: str, language: str | None = None
    ) -> TranscriptResult:
        try:
            return await self.gemini.transcribe(path, model, prompt, language)
        except Exception as e:
            log.warning("Gemini couldn't hear the recording (%s); OpenAI does it", e)
            backup = get_router().audio_model("transcribe")
            result = await self.openai_voice().transcribe(path, backup, prompt, language)
            result.model = backup
            return result

    async def speak(
        self, text: str, model: str, voice: str, speed: float, instructions: str
    ) -> AsyncIterator[bytes]:
        started = False
        try:
            async for chunk in self.gemini.speak(text, model, voice, speed, instructions):
                started = True
                yield chunk
            return
        except Exception as e:
            if started:  # half an answer already went out: don't repeat it in another voice
                raise
            log.warning("Gemini couldn't speak the answer (%s); OpenAI does it", e)
        async for chunk in self.openai_voice().speak(
            text, get_router().audio_model("speech"), get_setting("tts_voice"), speed, instructions
        ):
            yield chunk


def engine_voice(openai_voice):
    """The voice client for the engine chosen in Settings → Voice, picked fresh each time it's asked for."""

    def pick() -> "VoiceClient":
        if voice_engine() == "gemini":
            if GEMINI_VOICE is not None:
                return GeminiThenOpenAI(GEMINI_VOICE(), openai_voice)
            if get_settings().fake_ai:
                return FakeVoice()
            return GeminiThenOpenAI(GeminiVoice(), openai_voice)
        return openai_voice()

    return pick


def voice_models() -> tuple[str, str]:
    """(speech-to-text model, text-to-speech model) for the chosen engine."""
    r = get_router()
    if voice_engine() == "gemini":
        return r.audio_model("gemini_transcribe"), r.audio_model("gemini_speech")
    return r.audio_model("transcribe"), r.audio_model("speech")


def voice_name(settings: dict) -> str:
    return (settings.get("gemini_voice") or "Charon") if voice_engine() == "gemini" else settings["tts_voice"]


class FakeVoice:
    """For tests and FAKE_AI mode: no network, no cost."""

    async def transcribe(
        self, path: Path, model: str, prompt: str, language: str | None = None
    ) -> TranscriptResult:
        return TranscriptResult(
            text=f"(fake transcription of a {path.stat().st_size}-byte recording)",
            languages=["en"],
            seconds=None,
        )

    async def speak(
        self, text: str, model: str, voice: str, speed: float, instructions: str
    ) -> AsyncIterator[bytes]:
        # A tiny MP3 frame header followed by silence-ish bytes, in two pieces.
        yield b"\xff\xfb\x90\x64" + b"\x00" * 200
        yield b"\x00" * 200


def record_audio_usage(
    agent: str, model: str, mode: str, seconds: float, cost: float, conversation_id: int | None = None
) -> None:
    with session_scope() as s:
        s.add(
            Usage(
                agent=agent,
                model=model,
                mode=mode,
                conversation_id=conversation_id,
                extra={"seconds": round(seconds, 1)},
                cost_usd=cost,
            )
        )


@router.post("/api/voice/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    seconds: float | None = Form(default=None),
) -> dict:
    """Your recording -> text. The recording is kept so you can play it back."""
    return await transcribe_bytes(request.app.state.voice, await audio.read(), audio.content_type or "", seconds)


async def transcribe_bytes(voice_factory, data: bytes, content_type: str, seconds: float | None = None) -> dict:
    """A recording (from the dashboard or a WhatsApp voice note) -> saved file + text.
    Raises HTTPException with a plain message when it can't."""
    content_type = content_type.split(";")[0].strip().lower()
    ext = AUDIO_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(415, f"Unsupported audio type {content_type!r}")
    if not data:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The recording is too long (25 MB max).")
    try:
        budget_left()
    except BudgetExceeded as e:
        raise HTTPException(429, str(e)) from None

    audio_id = f"{uuid.uuid4().hex}.{ext}"
    path = audio_dir() / audio_id
    path.write_bytes(data)

    model_router = get_router()
    model = voice_models()[0]
    try:
        voice: VoiceClient = voice_factory()
        prompt = TRANSCRIBE_PROMPT.format(name=get_setting("user_name"))
        language = "ur" if get_setting("language") == "urdu" else None
        result = await voice.transcribe(path, model, prompt, language)
        retried = False
        if not is_noise(result.text, result.logprobs) and DEVANAGARI.search(result.text):
            # Urdu heard as Hindi: transcribe again, as Urdu.
            retried = True
            first_seconds = result.seconds
            result = await voice.transcribe(path, model, prompt, "ur")
            if result.seconds is not None and first_seconds is not None:
                result.seconds += first_seconds  # both runs are billed
    except NoApiKeyError as e:
        raise HTTPException(503, str(e)) from None
    except Exception as e:
        log.exception("Transcription failed")
        audit("tool_call", "transcribe", result="error", detail={"error": str(e)})
        raise HTTPException(502, f"Speech-to-text failed: {e}") from None

    model = result.model or model
    duration = result.seconds if result.seconds is not None else (seconds or 0.0)
    cost = duration / 60 * model_router.audio_price(model).get("per_minute", 0.0)
    record_audio_usage("transcriber", model, "voice", duration, cost)
    audit(
        "tool_call",
        "transcribe",
        detail={
            "model": model,
            "seconds": round(duration, 1),
            "languages": result.languages,
            "retried_as_urdu": retried,
        },
        cost_usd=cost,
    )
    noise = is_noise(result.text, result.logprobs)
    return {
        "audio_id": audio_id,
        # Breathing or background noise: nothing to send ("I didn't catch that").
        "text": "" if noise else result.text,
        "languages": result.languages,
        "seconds": round(duration, 1),
        "cost_usd": cost,
    }


@router.get("/api/audio/{audio_id}")
def get_audio(audio_id: str) -> FileResponse:
    path = audio_path(audio_id)
    if path is None:
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type=MEDIA_TYPES[path.suffix[1:]])


# ---- spoken replies ---------------------------------------------------------------

TTS_MAX_CHARS = 4000  # the API takes 4096 characters per request
CHARS_PER_MINUTE = 900  # rough speaking rate, for the cost estimate
SPEAK_INSTRUCTIONS = (
    "You are Junior Muneer, a warm and friendly AI assistant. Speak naturally and clearly, "
    "like a friend, with a relaxed pace. {accent} English words inside Urdu sentences "
    "should sound natural too."
)
PREVIEW_TEXT = (
    "السلام علیکم! میں جونیئر منیر ہوں، آپ کا دوست۔ "
    "Hello! I'm Junior Muneer, your friendly assistant."
)


def speak_instructions(settings: dict) -> str:
    return SPEAK_INSTRUCTIONS.format(accent=ACCENTS.get(settings["voice_accent"], ACCENTS["pakistani"]))


def speakable(markdown: str) -> str:
    """Markdown -> plain text that sounds right when read aloud."""
    text = re.sub(r"```.*?```", " (code shown on screen) ", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> their text
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^[ \t]*\|?[ \t]*:?-{2,}.*$", "", text, flags=re.M)  # table rules
    text = re.sub(  # table rows -> "cell, cell"
        r"^[ \t]*\|(.*)\|[ \t]*$",
        lambda m: ", ".join(c.strip() for c in m.group(1).split("|") if c.strip()),
        text,
        flags=re.M,
    )
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)  # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)  # bullets
    text = re.sub(r"[*_`>~]+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunks(text: str, limit: int = TTS_MAX_CHARS) -> list[str]:
    """Split long text at paragraph or sentence ends, each piece under the limit."""
    out: list[str] = []
    current = ""
    for part in re.split(r"(?<=[.!?\u06d4\u061f])\s+|\n+", text):
        if not part.strip():
            continue
        while len(part) > limit:
            out.append(part[:limit])
            part = part[limit:]
        if len(current) + len(part) + 1 > limit:
            out.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        out.append(current)
    return out


SPEAK_TIMEOUT_SECONDS = 180
# One generation per answer at a time: a second request waits, then gets the saved file.
_speak_locks: dict[int, asyncio.Lock] = {}


def _saved_speech(message_id: int) -> Path | None:
    with session_scope() as s:
        message = s.get(Message, message_id)
        if message is None or message.role != "assistant":
            raise HTTPException(404, "No answer with that id")
        return audio_path(message.audio_file) if message.audio_file else None


@router.get("/api/voice/speak/{message_id}.mp3")
async def speak(request: Request, message_id: int):
    """Read one of his answers aloud. Streams while it's made; saved and reused after."""
    lock = _speak_locks.setdefault(message_id, asyncio.Lock())
    await lock.acquire()
    try:
        saved = _saved_speech(message_id)
        if saved is not None:
            lock.release()
            return FileResponse(saved, media_type="audio/mpeg")
        with session_scope() as s:
            message = s.get(Message, message_id)
            text = speakable(message.content)
            conversation_id = message.conversation_id
        if not text:
            raise HTTPException(400, "Nothing to read aloud")
        try:
            budget_left()
        except BudgetExceeded as e:
            raise HTTPException(429, str(e)) from None
        try:
            voice: VoiceClient = request.app.state.voice()
        except NoApiKeyError as e:
            raise HTTPException(503, str(e)) from None
    except BaseException:
        if lock.locked():
            lock.release()
        raise

    settings = all_settings()
    model = voice_models()[1]
    speed = float(settings["tts_speed"])

    async def generate() -> AsyncIterator[bytes]:
        audio = bytearray()
        try:
            async with asyncio.timeout(SPEAK_TIMEOUT_SECONDS):
                for piece in chunks(text):  # MP3 pieces join cleanly
                    async for chunk in voice.speak(
                        piece, model, voice_name(settings), speed, speak_instructions(settings)
                    ):
                        audio.extend(chunk)
                        yield chunk
        except Exception as e:  # the browser just stops playing; the reason is logged
            log.exception("Text-to-speech failed")
            audit(
                "tool_call",
                "speak",
                result="error",
                detail={"error": f"{type(e).__name__}: {e}"},
                conversation_id=conversation_id,
            )
            return
        finally:
            lock.release()
        _store_speech(message_id, conversation_id, bytes(audio), text, model, settings, speed)

    return StreamingResponse(generate(), media_type="audio/mpeg")


def _store_speech(message_id: int, conversation_id: int | None, audio: bytes, text: str, model: str, settings: dict, speed: float) -> None:
    """Keep a spoken answer with its message (played back later without paying again), and count its cost."""
    audio_id = f"{uuid.uuid4().hex}.mp3"
    (audio_dir() / audio_id).write_bytes(audio)
    seconds = len(text) / CHARS_PER_MINUTE * 60 / speed
    cost = len(text) / CHARS_PER_MINUTE * get_router().audio_price(model).get("per_minute", 0.0)
    record_audio_usage("speaker", model, "voice", seconds, cost, conversation_id)
    audit(
        "tool_call",
        "speak",
        detail={"model": model, "voice": voice_name(settings), "characters": len(text)},
        cost_usd=cost,
        conversation_id=conversation_id,
    )
    with session_scope() as s:
        message = s.get(Message, message_id)
        message.audio_file = audio_id
        message.audio_seconds = round(seconds, 1)


async def speak_message(voice_factory, message_id: int) -> bytes:
    """One of his answers as MP3 (for a WhatsApp voice reply). Reuses it if it was spoken before.
    Raises if it can't be made (no key, the daily cap, the speech service failing)."""
    saved = _saved_speech(message_id)
    if saved is not None:
        return saved.read_bytes()
    with session_scope() as s:
        message = s.get(Message, message_id)
        text = speakable(message.content)
        conversation_id = message.conversation_id
    if not text:
        return b""
    budget_left()
    voice: VoiceClient = voice_factory()
    settings = all_settings()
    model = voice_models()[1]
    speed = float(settings["tts_speed"])
    audio = bytearray()
    async with asyncio.timeout(SPEAK_TIMEOUT_SECONDS):
        for piece in chunks(text):
            async for chunk in voice.speak(piece, model, voice_name(settings), speed, speak_instructions(settings)):
                audio.extend(chunk)
    _store_speech(message_id, conversation_id, bytes(audio), text, model, settings, speed)
    return bytes(audio)


@router.get("/api/voice/preview/{voice}/{accent}.mp3")
async def preview(request: Request, voice: str, accent: str):
    """A short Urdu + English sample of a voice and accent, made once and kept."""
    if voice not in TTS_VOICES or accent not in ACCENTS:
        raise HTTPException(404, "Unknown voice or accent")
    path = audio_dir() / f"preview-{voice}-{accent}.mp3"
    if path.exists():
        return FileResponse(path, media_type="audio/mpeg")
    try:
        budget_left()
    except BudgetExceeded as e:
        raise HTTPException(429, str(e)) from None
    model = get_router().audio_model("speech")
    try:
        client: VoiceClient = request.app.state.openai_voice()  # these are OpenAI's voices, whatever the engine
        audio = bytearray()
        async for chunk in client.speak(
            PREVIEW_TEXT, model, voice, 1.0, speak_instructions({"voice_accent": accent})
        ):
            audio.extend(chunk)
    except NoApiKeyError as e:
        raise HTTPException(503, str(e)) from None
    except Exception as e:
        log.exception("Voice preview failed")
        raise HTTPException(502, f"Couldn't make the preview: {e}") from None
    path.write_bytes(audio)
    cost = len(PREVIEW_TEXT) / CHARS_PER_MINUTE * get_router().audio_price(model).get("per_minute", 0)
    record_audio_usage("speaker", model, "voice", len(PREVIEW_TEXT) / CHARS_PER_MINUTE * 60, cost)
    return FileResponse(path, media_type="audio/mpeg")
