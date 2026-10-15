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


@router.get("/api/settings")
def get_settings_api() -> dict:
    return all_settings()


@router.patch("/api/settings")
def update_settings(body: SettingsUpdate) -> dict:
    before = all_settings()
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        if before[key] != value:
            set_setting(key, value)
            audit("setting", key, detail={"before": before[key], "after": value})
    return all_settings()


@router.get("/api/voices")
def voices() -> list[str]:
    return list(TTS_VOICES)


@router.get("/api/voices/natural")
def natural_voices() -> list[str]:
    return list(NATURAL_VOICES)


MODEL_LABELS = {
    "gpt-6-astra": "OpenAI GPT-6 Astra (best, most expensive)",
    "gpt-6.1-sol": "OpenAI GPT-6.1 Sol (strong)",
    "gpt-6-sol": "OpenAI GPT-6 Sol",
    "gpt-6-luna": "OpenAI GPT-6 Luna (fast, cheap)",
    "deepseek:deepseek-flash": "DeepSeek Flash (very cheap)",
    "deepseek:deepseek-v4-pro": "DeepSeek V4 Pro (slow: thinks ~25 s before answering)",
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
        choices.append(
            {
                "model": model,
                "label": MODEL_LABELS.get(model, model),
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
