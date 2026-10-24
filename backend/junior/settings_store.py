"""Your settings, stored in the database (the Settings page edits them)."""

from copy import deepcopy
from typing import Any

from junior.db import Setting, session_scope

DEFAULTS: dict[str, Any] = {
    "user_name": "Muneer",
    # match · english · urdu
    "language": "match",
    "timezone": "Asia/Karachi",
    "daily_cap_usd": 5.0,
    "task_budget_usd": 0.5,
    "task_timeout_seconds": 600,
    "task_max_retries": 1,
    "paused": False,
    # Voice (phase 1)
    "tts_voice": "marin",
    # pakistani · indian · neutral
    "voice_accent": "pakistani",
    "tts_speed": 1.0,
    # Read answers to voice messages aloud automatically.
    "voice_autoplay": True,
    # Live calls cost the most, so they have a daily limit.
    "call_minutes_per_day": 30,
    # natural (full realtime model) · economy (mini)
    "call_quality": "natural",
    # Which engine runs live calls: OpenAI Realtime (above), or Google Gemini Live (needs GEMINI_API_KEY).
    "computer_enabled": True,  # Phase 9: the computer tools (Settings -> Computer)
    "computer_folders": None,  # None = Desktop, Documents and Downloads; else your list of full paths
    "voice_engine": "openai",  # voice messages: "openai" or "gemini" (Settings -> Voice)
    "voice_hear_model": "",  # "" = the engine's default (agents/models.toml)
    "voice_speak_model": "",
    "voice_provider_model": "openai-realtime",
    # Gemini Live's voice (Gemini has its own voices).
    "gemini_voice": "Charon",
    # patient · balanced · quick: how soon he answers when you pause
    "turn_taking": "balanced",
    # headset · laptop · off: noise reduction to suit your microphone in calls
    "mic_type": "headset",
    # Text models (Settings -> Models). "" = the default from agents/models.toml.
    "main_model": "",
    "helper_model": "",
    # Web search engine: openai (hosted search through a small helper) · deepseek (DeepSeek's Search API, cheaper).
    "web_search_provider": "openai",
    # Reading photos: openai (its small vision model) · deepseek (DeepSeek V4.1 Flash, cheaper).
    "vision_provider": "openai",
    # Your profile (Profile page). Kept here, edited through /api/profile.
    "profile": {},
    # Phase 3: at most this many posts per platform per day through the APIs (Safety Guard).
    "api_posts_per_day": 5,
    # News (Phase 2b): both digests are built each morning at this local time.
    "news_digest_enabled": True,
    "news_digest_time": "07:30",
    # The day's top 5 AI news emailed to your Gmail after the morning digest (needs GMAIL_* in backend/.env).
    "news_email_enabled": True,
    "news_emailed_on": "",
    # Phase 4: the email watcher sorts new Gmail every 5 minutes; important ones go to your WhatsApp.
    "email_watch_enabled": True,
    "email_notify_whatsapp": True,
    "email_checked_at": "",
    "email_watch_since": "",
    "email_alerts_waiting": [],
    # Phase 7: the morning briefing (yesterday, today's agenda, news), once a day at this local time.
    "briefing_enabled": True,
    "briefing_time": "08:00",
    # Phase 7: the weekly memory tidy-up (duplicates and outdated memories are archived, restorable).
    "memory_tidy_enabled": True,
    "memory_tidied_at": "",
    # Phase 8: WhatsApp sessions. A new WhatsApp chat starts after this many quiet hours (0: every message),
    # and the new chat can start with a summary of the previous one.
    "whatsapp_session_hours": 12,
    "whatsapp_carry_summary": True,
    # Phase 7: when your own feeds were last read (every 3 hours).
    "feeds_read_at": "",
    # Permission rules (/api/permissions): ask_all · rules, and your rule per action type.
    "permission_mode": "rules",
    "permission_rules": {},
}
# Voices that work both for spoken replies and in live calls. Marin and Cedar are
# OpenAI's newest, most natural voices, so they come first.
TTS_VOICES = (
    "marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse",
)
NATURAL_VOICES = ("marin", "cedar")
TURN_TAKING = {"patient": "low", "balanced": "auto", "quick": "high"}
NOISE_REDUCTION = {"headset": "near_field", "laptop": "far_field", "off": None}
# How he sounds. Used for spoken replies and live calls.
ACCENTS = {
    "pakistani": (
        "Speak with a natural Pakistani accent. Speak Urdu like a native speaker from Lahore "
        "or Karachi, and English the way an educated Pakistani speaks it."
    ),
    "indian": (
        "Speak with a natural North Indian accent. Speak Hindustani (Hindi-Urdu) like a "
        "native speaker from Delhi, and English the way an educated Indian speaks it."
    ),
    "neutral": (
        "Speak English with a clear, neutral international accent. Pronounce Urdu correctly, "
        "like a native speaker."
    ),
}
LANGUAGES = {"match", "english", "urdu"}


def get_setting(key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key!r}")
    with session_scope() as s:
        row = s.get(Setting, key)
        # A copy, so changing the result never changes the defaults.
        return deepcopy(DEFAULTS[key] if row is None else row.value)


def set_setting(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key!r}")
    with session_scope() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=value))
        else:
            row.value = value


def all_settings() -> dict[str, Any]:
    with session_scope() as s:
        stored = {row.key: row.value for row in s.query(Setting).all()}
    return {k: stored.get(k, v) for k, v in DEFAULTS.items()}
