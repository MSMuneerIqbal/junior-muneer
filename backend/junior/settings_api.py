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
    user_name: str | None = Field(default=None, min_length=1, max_length=50)
    language: Literal["match", "english", "urdu"] | None = None
    timezone: str | None = None
    daily_cap_usd: float | None = Field(default=None, ge=0, le=1000)
    tts_voice: Literal[TTS_VOICES] | None = None  # type: ignore[valid-type]
    voice_accent: Literal["pakistani", "indian", "neutral"] | None = None
    tts_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    voice_autoplay: bool | None = None
    call_minutes_per_day: int | None = Field(default=None, ge=0, le=600)
    call_quality: Literal["natural", "economy"] | None = None
    turn_taking: Literal["patient", "balanced", "quick"] | None = None
    mic_type: Literal["headset", "laptop", "off"] | None = None
    main_model: str | None = Field(default=None, max_length=100)
    helper_model: str | None = Field(default=None, max_length=100)
    web_search_provider: Literal["openai", "deepseek"] | None = None
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
    briefing_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("main_model", "helper_model")
    @classmethod
    def _known_model(cls, v: str | None) -> str | None:
        if v and v not in get_router().prices:
            raise ValueError(f"Unknown model {v!r}; it needs a price in agents/models.toml")
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
NOT_HERE = {"profile", "permission_mode", "permission_rules", "memory_tidied_at", "feeds_read_at", "news_emailed_on",
            "email_checked_at", "email_watch_since", "email_alerts_waiting"}


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
        "DeepSeek Flash",
        "Very cheap and quick. Can stall when DeepSeek is busy (OpenAI steps in after 20 s).",
        "fast",
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
