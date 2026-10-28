"""Settings API.

    GET   /api/settings   your settings
    PATCH /api/settings   change some of them (checked; each change is in the audit log)
    GET   /api/models     which model each agent uses (view only; edit agents/models.toml)
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from junior.audit import audit
from junior.agent.builder import chosen_model
from junior.models import get_router
from junior.settings_store import NATURAL_VOICES, TTS_VOICES, all_settings, set_setting
from junior.timeutil import zone

router = APIRouter()


class SettingsUpdate(BaseModel):
    drive_share_default: Literal["private", "reader", "writer"] | None = None
    user_name: str | None = Field(default=None, min_length=1, max_length=50)
    language: Literal["match", "english", "urdu"] | None = None
    timezone: str | None = None
    daily_cap_usd: float | None = Field(default=None, ge=0, le=1000)
    chat_budget_usd: float | None = Field(default=None, ge=0.01, le=10, allow_inf_nan=False)
    chat_max_model_calls: int | None = Field(default=None, ge=1, le=24)
    max_output_tokens: int | None = Field(default=None, ge=512, le=16000)
    task_budget_usd: float | None = Field(default=None, ge=0.01, le=10, allow_inf_nan=False)
    task_timeout_seconds: int | None = Field(default=None, ge=30, le=1800)
    task_max_retries: int | None = Field(default=None, ge=0, le=2)
    tts_voice: Literal[TTS_VOICES] | None = None  # type: ignore[valid-type]
    voice_accent: Literal["pakistani", "indian", "neutral"] | None = None
    tts_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    voice_autoplay: bool | None = None
    call_minutes_per_day: int | None = Field(default=None, ge=0, le=600)
    call_quality: Literal["natural", "economy"] | None = None
    voice_engine: Literal["openai", "gemini"] | None = None
    voice_hear_model: str | None = Field(default=None, max_length=100)  # "" = the engine's default
    voice_speak_model: str | None = Field(default=None, max_length=100)
    voice_provider_model: Literal["openai-realtime", "gemini-3.8-live", "gemini-2.5-flash-native-audio-preview-12-2025"] | None = None
    gemini_voice: Literal["Charon", "Puck", "Kore", "Fenrir", "Aoede", "Orus", "Leda", "Zephyr"] | None = None
    turn_taking: Literal["patient", "balanced", "quick"] | None = None
    mic_type: Literal["headset", "laptop", "off"] | None = None
    main_model: str | None = Field(default=None, max_length=100)
    helper_model: str | None = Field(default=None, max_length=100)
    web_search_provider: Literal["openai", "deepseek", "gemini"] | None = None
    vision_provider: Literal["openai", "deepseek"] | None = None
    api_posts_per_day: int | None = Field(default=None, ge=0, le=50)
    news_digest_enabled: bool | None = None
    news_digest_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    news_email_enabled: bool | None = None
    email_watch_enabled: bool | None = None
    email_notify_whatsapp: bool | None = None
    briefing_enabled: bool | None = None
    memory_tidy_enabled: bool | None = None
    whatsapp_session_hours: Literal[0, 6, 12, 24] | None = None
    whatsapp_carry_summary: bool | None = None
    whatsapp_action_mode: Literal["ask_all", "rules"] | None = None
    computer_enabled: bool | None = None
    computer_all_files: bool | None = None
    briefing_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("main_model", "helper_model")
    @classmethod
    def _known_model(cls, v: str | None) -> str | None:
        if v and v not in get_router().prices:
            raise ValueError(f"Unknown model {v!r}; it needs a price in agents/models.toml")
        return v

    @field_validator("voice_hear_model", "voice_speak_model")
    @classmethod
    def _known_voice_model(cls, v: str | None, info) -> str | None:
        from junior.voice import VOICE_CHOICES

        if v:
            job = "hear" if info.field_name == "voice_hear_model" else "speak"
            known = {m for jobs in VOICE_CHOICES.values() for m, _, _ in jobs[job]}
            if v not in known:
                raise ValueError(f"Unknown voice model {v!r}; pick one from Settings -> Voice")
        return v

    @field_validator("user_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name can't be empty")
        return v.strip() if v else v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and (zone(v).key != v):
            raise ValueError(f"Unknown time zone {v!r} (use names like Asia/Karachi)")
        return v


# Edited through their own pages and endpoints (/api/profile, /api/permissions).
NOT_HERE = {"profile", "permission_mode", "permission_rules", "permission_unlocked_rules", "memory_tidied_at", "feeds_read_at", "news_emailed_on",
            "email_checked_at", "email_watch_since", "email_alerts_waiting", "computer_folders"}


@router.get("/api/settings")
def get_settings_api() -> dict:
    return {k: v for k, v in all_settings().items() if k not in NOT_HERE}


@router.patch("/api/settings")
def update_settings(body: SettingsUpdate) -> dict:
    before = all_settings()
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        if before[key] != value:
            set_setting(key, value)
            audit("setting", key, detail={"before": before[key], "after": value})
    return {k: v for k, v in all_settings().items() if k not in NOT_HERE}


@router.get("/api/voices")
def voices() -> list[str]:
    return list(TTS_VOICES)


@router.get("/api/voices/natural")
def natural_voices() -> list[str]:
    return list(NATURAL_VOICES)


# How each text model shows in Settings: name, a short note, and its speed as
# measured on this PC (time to the first words of an answer, Oct 2026).
MODEL_INFO = {
    "gpt-6.1-sol": ("GPT-6.1 Sol", "Strong and reliable. The default.", "medium"),
    "gpt-6-luna": ("GPT-6 Luna", "Fastest and cheapest; fine for everyday chat.", "fast"),
    "gpt-6-sol": ("GPT-6 Sol", "Strong, slightly older.", "medium"),
    "gpt-6-astra": ("GPT-6 Astra", "OpenAI's best, and the most expensive.", "medium"),
    "deepseek:deepseek-flash": (
        "DeepSeek V4.1 Flash",
        "Very cheap and quick, and sees images. Can stall when DeepSeek is busy (OpenAI steps in after 20 s).",
        "fast",
    ),
    "gemini:gemini-3.8-flash": (
        "Gemini 3.8 Flash",
        "Google's smartest Flash. On a free key it waits about a minute per reply (OpenAI steps in after 20 s); quick on a paid key.",
        "slow",
    ),
    "gemini:gemini-3.1-flash-lite": (
        "Gemini 3.1 Flash-Lite",
        "Google's fastest and cheapest: answers in about 2 s, free tier. The best Gemini choice on a free key.",
        "fast",
    ),
    "gemini:gemini-2.5-flash": (
        "Gemini 2.5 Flash",
        "Older Flash, steady and cheap; free tier.",
        "fast",
    ),
    "gemini:gemini-4-argon": (
        "Gemini 4 Argon",
        "Google's heavy flagship for hard reasoning. Paid only: a free key can't use it.",
        "medium",
    ),
    "deepseek:deepseek-v4-pro": (
        "DeepSeek V4 Pro",
        "Thinks before every answer: about 25 s, even for 'hi'.",
        "slow",
    ),
}


@router.get("/api/models/choices")
def model_choices() -> dict:
    """Text models you can pick in Settings, and whether each is ready to use."""
    from junior.config import get_settings

    model_router = get_router()
    settings = get_settings()
    choices = []
    for model in model_router.text_models():
        provider = model_router.provider_of(model)
        info = model_router.providers.get(provider, {})
        ready = bool(
            settings.openai_api_key
            if provider == "openai"
            else getattr(settings, info.get("key_env", "").lower(), "")
        )
        price = model_router.price(model)
        name, note, speed = MODEL_INFO.get(model, (model, "", "medium"))
        choices.append(
            {
                "model": model,
                "label": name,
                "note": note,
                "speed": speed,
                "provider": info.get("label", "OpenAI") if provider != "openai" else "OpenAI",
                "ready": ready,
                "key_env": info.get("key_env", "OPENAI_API_KEY"),
                "price_per_million": {"input": price.input, "output": price.output},
            }
        )
    return {
        "choices": choices,
        "defaults": {
            "main_model": model_router.model_for("junior_muneer", "strong"),
            "helper_model": model_router.model_for("summarizer", "small"),
        },
    }


@router.get("/api/models")
def models(request: Request) -> dict:
    model_router = get_router()
    registry = request.app.state.registry
    agents = []
    for name in registry.names():
        spec = registry.get(name)
        model = chosen_model(spec, model_router)
        agents.append(
            {
                "agent": name,
                "description": spec.description,
                "tier": model_router.agents.get(name, spec.model),
                "model": model,
                "price_per_million": vars(model_router.price(model)),
            }
        )
    if not agents:
        raise HTTPException(500, "No agents loaded")
    return {"tiers": model_router.tiers, "agents": agents}
