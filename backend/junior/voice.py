"""Voice messages: speech-to-text for your recordings, text-to-speech for his answers.

    POST /api/voice/transcribe   upload a recording -> {audio_id, text, languages, seconds}
    GET  /api/audio/{audio_id}   play a saved recording or spoken answer

Recordings and spoken answers are saved in data/uploads/audio.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from openai import AsyncOpenAI

from junior.agent.builder import NoApiKeyError
from junior.audit import audit
from junior.config import get_settings
from junior.costs import BudgetExceeded, budget_left
from junior.db import Usage, session_scope
from junior.models import get_router
from junior.settings_store import get_setting

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
TRANSCRIBE_PROMPT = (
    "The speaker is {name}, talking to their AI assistant Junior Muneer. "
    "They may speak English, Urdu or a mix of both."
)


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


class VoiceClient(Protocol):
    async def transcribe(self, path: Path, model: str, prompt: str) -> TranscriptResult: ...


class OpenAIVoice:
    def __init__(self) -> None:
        key = get_settings().openai_api_key
        if not key:
            raise NoApiKeyError("No OpenAI API key yet. Paste it into backend/.env.")
        self.client = AsyncOpenAI(api_key=key)

    async def transcribe(self, path: Path, model: str, prompt: str) -> TranscriptResult:
        with path.open("rb") as f:
            result = await self.client.audio.transcriptions.create(
                model=model, file=f, prompt=prompt
            )
        usage = getattr(result, "usage", None)
        seconds = getattr(usage, "seconds", None) if usage is not None else None
        languages = [
            getattr(lang, "code", None) or str(lang)
            for lang in (getattr(result, "languages", None) or [])
        ]
        return TranscriptResult(text=result.text.strip(), languages=languages, seconds=seconds)


class FakeVoice:
    """For tests and FAKE_AI mode: no network, no cost."""

    async def transcribe(self, path: Path, model: str, prompt: str) -> TranscriptResult:
        return TranscriptResult(
            text=f"(fake transcription of a {path.stat().st_size}-byte recording)",
            languages=["en"],
            seconds=None,
        )


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
    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    ext = AUDIO_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(415, f"Unsupported audio type {content_type!r}")
    data = await audio.read()
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
    model = model_router.audio_model("transcribe")
    try:
        voice: VoiceClient = request.app.state.voice()
        prompt = TRANSCRIBE_PROMPT.format(name=get_setting("user_name"))
        result = await voice.transcribe(path, model, prompt)
    except NoApiKeyError as e:
        raise HTTPException(503, str(e)) from None
    except Exception as e:
        log.exception("Transcription failed")
        audit("tool_call", "transcribe", result="error", detail={"error": str(e)})
        raise HTTPException(502, f"Speech-to-text failed: {e}") from None

    duration = result.seconds if result.seconds is not None else (seconds or 0.0)
    cost = duration / 60 * model_router.audio_price(model).get("per_minute", 0.0)
    record_audio_usage("transcriber", model, "voice", duration, cost)
    audit(
        "tool_call",
        "transcribe",
        detail={"model": model, "seconds": round(duration, 1), "languages": result.languages},
        cost_usd=cost,
    )
    return {
        "audio_id": audio_id,
        "text": result.text,
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
