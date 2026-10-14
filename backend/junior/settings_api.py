"""Settings API.

    GET   /api/settings   your settings
    PATCH /api/settings   change some of them (checked; each change is in the audit log)
    GET   /api/models     which model each agent uses (view only; edit agents/models.toml)
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from junior.audit import audit
from junior.models import get_router
from junior.settings_store import TTS_VOICES, all_settings, set_setting
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


@router.get("/api/models")
def models(request: Request) -> dict:
    model_router = get_router()
    registry = request.app.state.registry
    agents = []
    for name in registry.names():
        spec = registry.get(name)
        model = model_router.model_for(name, spec.model)
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
