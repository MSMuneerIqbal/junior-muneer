"""Your settings, stored in the database (the Settings page edits them)."""

from typing import Any

from junior.db import Setting, session_scope

DEFAULTS: dict[str, Any] = {
    "user_name": "Muneer",
    # match · english · urdu
    "language": "match",
    "timezone": "Asia/Karachi",
    "daily_cap_usd": 5.0,
    "paused": False,
    # Voice (phase 1)
    "tts_voice": "marin",
    "tts_speed": 1.0,
    # Read answers to voice messages aloud automatically.
    "voice_autoplay": True,
    # Live calls cost the most, so they have a daily limit.
    "call_minutes_per_day": 30,
}
TTS_VOICES = (
    "marin", "cedar", "alloy", "ash", "ballad", "coral", "echo",
    "fable", "nova", "onyx", "sage", "shimmer", "verse",
)
LANGUAGES = {"match", "english", "urdu"}


def get_setting(key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key!r}")
    with session_scope() as s:
        row = s.get(Setting, key)
        return DEFAULTS[key] if row is None else row.value


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
