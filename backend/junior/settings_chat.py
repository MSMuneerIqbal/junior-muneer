"""Change some settings by asking in chat ("switch to DeepSeek pro", "voice mein Urdu", "WhatsApp: new chat every 6 hours").

Only everyday settings. The money and safety ones (daily spending limit, pause, call minutes, API posts per day,
permissions) stay on the Settings page: a chat message, or a pasted text that tricks him, can't change them.
Like memory, a change needs your own words from your own message, and nothing outside may be in the turn.
"""

from typing import Any

from pydantic import ValidationError

from junior.audit import audit
from junior.settings_api import MODEL_INFO, SettingsUpdate
from junior.settings_store import all_settings, set_setting

# What he may change, and how it reads in chat.
CHANGEABLE: dict[str, str] = {
    "main_model": "Main model (chat, WhatsApp)",
    "helper_model": "Helper model (writing team, news, other helpers)",
    "web_search_provider": "Web search engine: openai, deepseek (cheaper) or gemini (Google Search, free tier)",
    "vision_provider": "Who reads photos: openai or deepseek (DeepSeek V4.1 Flash, cheaper)",
    "language": "Reply language: match, english or urdu",
    "tts_voice": "Speaking voice",
    "voice_accent": "Accent: pakistani, indian or neutral",
    "tts_speed": "Speaking speed: 0.5 to 2.0",
    "voice_autoplay": "Read answers to voice messages aloud: on or off",
    "turn_taking": "In calls, how soon he answers: patient, balanced or quick",
    "mic_type": "Microphone in calls: headset, laptop or off",
    "whatsapp_session_hours": "New WhatsApp chat after 6, 12 or 24 quiet hours, or 0 for every message",
    "whatsapp_carry_summary": "Start a new WhatsApp chat with a summary of the previous one: on or off",
    "briefing_enabled": "Morning briefing: on or off",
    "briefing_time": "Morning briefing time, HH:MM",
    "news_digest_enabled": "Daily news digests: on or off",
    "news_digest_time": "News digests time, HH:MM",
    "news_email_enabled": "Email the top 5 AI news to their Gmail each morning: on or off",
    "email_watch_enabled": "Watch their Gmail inbox and sort new emails: on or off",
    "email_notify_whatsapp": "Tell them about important new emails on WhatsApp: on or off",
    "memory_tidy_enabled": "Weekly memory tidy-up: on or off",
}
# Only on the Settings page, never from chat.
PAGE_ONLY = {
    "daily_cap_usd": "the daily spending limit",
    "paused": "pausing Junior Muneer",
    "call_minutes_per_day": "the daily call minutes",
    "call_quality": "call quality",
    "api_posts_per_day": "API posts per day",
    "user_name": "your name",
    "timezone": "the time zone",
    "permission_rules": "permissions",
    "permission_mode": "permissions",
}
_ON = {"on", "true", "yes", "1", "enable", "enabled", "haan", "han"}
_OFF = {"off", "false", "no", "0", "disable", "disabled", "nahi", "nahin"}


def show(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if value == "":
        return "the default"
    return str(value)


def model_names() -> str:
    return ", ".join(f"{model} ({info[0]})" for model, info in MODEL_INFO.items())


def current_settings() -> str:
    """The settings he can change, with their values now."""
    settings = all_settings()
    lines = [f"- {key} = {show(settings[key])}: {label}" for key, label in CHANGEABLE.items()]
    return (
        "Settings you can change from chat:\n" + "\n".join(lines)
        + f"\nModels: {model_names()} ('' = the default)."
        + "\nOnly on the Settings page: " + ", ".join(sorted(set(PAGE_ONLY.values()))) + "."
    )


def _parse(key: str, value: str) -> Any:
    text = value.strip()
    current = all_settings()[key]
    if isinstance(current, bool):
        word = text.casefold()
        if word in _ON:
            return True
        if word in _OFF:
            return False
        raise ValueError("say on or off")
    if key == "whatsapp_session_hours":
        word = text.casefold().removesuffix("hours").removesuffix("h").strip()
        return 0 if word in {"every message", "every", "0"} else int(word)
    if key == "tts_speed":
        return float(text)
    if key in {"language", "voice_accent", "turn_taking", "mic_type", "tts_voice", "web_search_provider", "vision_provider"}:
        return text.casefold()
    if key.endswith("_model") and text.casefold() == "default":
        return ""
    return text


def change_setting_for(context: Any, setting: str, value: str, your_words: str) -> str:
    """The rules for changing a setting from chat (see the module notes)."""
    from junior.agent.tools import MIN_QUOTE_CHARS, _normalize
    from junior.db import Message, session_scope
    from sqlalchemy import select

    if setting in PAGE_ONLY:
        return (
            f"NOT changed: {PAGE_ONLY[setting]} can only be changed on the Settings page "
            "(it protects money and safety). Tell the user where to find it."
        )
    if setting not in CHANGEABLE:
        return f"NOT changed: there is no setting {setting!r}. These can be changed: {', '.join(CHANGEABLE)}."
    if context.outside_content_seen or context.paste:
        return (
            "NOT changed: this turn includes outside text (a paste, web results or past chats), so settings "
            "can't change now. Ask the user to say it again in a new message on its own."
        )
    if context.background:
        return "NOT changed: settings change only in chat, not in background work."
    quote = _normalize(your_words)
    if len(quote) < MIN_QUOTE_CHARS:
        return "NOT changed: copy the user's own words asking for this change (a few words) into your_words."
    with session_scope() as s:
        mine = s.scalars(
            select(Message.content).where(Message.id.in_(context.user_message_ids), Message.source == "user")
        ).all()
    if not any(quote in _normalize(content) for content in mine):
        return "NOT changed: those words aren't in the user's own messages. Change settings only when they ask."

    try:
        new = _parse(setting, value)
        SettingsUpdate.model_validate({setting: new})
    except (ValueError, ValidationError) as e:
        hint = f" Models: {model_names()}." if setting.endswith("_model") else ""
        why = e.errors()[0]["msg"] if isinstance(e, ValidationError) else str(e)
        return f"NOT changed: {value!r} doesn't work for {setting} ({why}).{hint}"

    before = all_settings()[setting]
    if before == new:
        return f"No change: {setting} is already {show(new)}."
    set_setting(setting, new)
    context.settings[setting] = new
    audit(
        "setting",
        setting,
        detail={"before": before, "after": new, "by": "chat"},
        conversation_id=context.conversation_id,
    )
    return (
        f"Changed {setting}: {show(before)} -> {show(new)}. Tell the user in one line; they can change it back "
        "by asking, or on the Settings page. A new model is used from their next message."
    )
