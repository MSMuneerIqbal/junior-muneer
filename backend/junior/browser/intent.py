"""Bind automatic browser actions to an actual user request and its website."""
import re
from urllib.parse import urljoin

from junior import gate
from junior.browser.network import BrowserRefused, origin


def authorizes(context, spec, details):
    words = (context.user_text or "").strip()
    if not words or not gate.you_said(context, words):
        return False
    urls = re.findall(r"https?://[^\s<>\"']+", words, re.IGNORECASE)
    try:
        sites = {origin(u.rstrip(".,;:!?)]}")) for u in urls}
        page = spec.url if spec.kind == "navigate" else details.get("page_url", "")
        if not page or origin(page) not in sites:
            return False
        for target in (details.get("target_href"), (details.get("form") or {}).get("action")):
            if target and origin(urljoin(page, target)) not in sites:
                return False
    except BrowserRefused:
        return False
    if spec.kind == "fill":
        profile = context.settings.get("profile") or {}
        approved = [str(context.settings.get("user_name") or ""), str(profile.get("email") or "")]
        value = spec.text.strip().casefold()
        if not value or (value not in words.casefold() and value not in [v.strip().casefold() for v in approved if v.strip()]):
            return False
    if spec.kind in ("fill", "click") and not re.search(r"\b(open|visit|browse|find|search|read|click|fill|write|send|submit|message|contact|form|bhej|bhejo|likho|kholo)\b|بھیج|لکھ|کھول|تلاش|پیغام", words, re.I):
        return False
    if spec.kind == "click" and (details.get("element_type") == "submit" or re.search(r"\b(send|submit|post|publish)\b", str(details.get("target_label", "")), re.I)):
        if not re.search(r"\b(send|submit|post|publish|bhej|bhejo)\b|بھیج", words, re.I):
            return False
    return True


def persisted_authorizes(item):
    from junior.agent.context import TurnContext
    from junior.browser.runtime import BrowserAction
    from junior.db import Message, session_scope
    from junior.settings_store import all_settings
    ident = item.meta.get("browser_user_message_id")
    if not isinstance(ident, int) or item.action_type != "computer.browser.input":
        return False
    with session_scope() as session:
        message = session.get(Message, ident)
        if not message or message.source != "user" or message.conversation_id != item.conversation_id:
            return False
        words = message.content
    try:
        spec = BrowserAction.model_validate_json(item.text)
    except ValueError:
        return False
    context = TurnContext(conversation_id=item.conversation_id, settings=all_settings(), user_text=words, user_message_ids=[ident])
    return authorizes(context, spec, item.meta)
