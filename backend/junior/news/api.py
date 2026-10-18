"""News API (P2b-05).

    GET  /api/news/{topic}           the latest digest (topic: ai or pakistan), or null
    POST /api/news/{topic}/refresh   read the official sources again and build a new digest (about a minute)
    GET  /api/news-sources           the official sources and whether rankings are on
"""

from fastapi import APIRouter, HTTPException, Request

from junior.agent.builder import NoApiKeyError
from junior.config import get_settings
from junior.costs import BudgetExceeded
from junior.news.digest import TOPICS, latest_digest, refresh_digest
from junior.news.sources import load_sources

router = APIRouter()


def _topic(topic: str) -> str:
    if topic not in TOPICS:
        raise HTTPException(404, f"No news topic {topic!r}; use one of {list(TOPICS)}.")
    return topic


@router.get("/api/news/{topic}")
def get_news(topic: str) -> dict:
    return {"topic": _topic(topic), "digest": latest_digest(topic)}


@router.post("/api/news/{topic}/refresh")
async def refresh_news(topic: str, request: Request) -> dict:
    _topic(topic)
    try:
        provider = request.app.state.chat.model_provider()
        digest = await refresh_digest(topic, request.app.state.registry, provider)
    except NoApiKeyError as e:
        raise HTTPException(400, str(e)) from None
    except BudgetExceeded as e:
        raise HTTPException(409, str(e)) from None
    return {"topic": topic, "digest": digest}


@router.get("/api/news-email")
def news_email_status() -> dict:
    """The daily top 5 email: set up or not, on or off, last sent."""
    from junior.mailer import configured, my_address
    from junior.news.mail import ACTION
    from junior.permissions import rule_for
    from junior.settings_store import all_settings

    settings = all_settings()
    return {
        "configured": configured(),
        "address": my_address() if configured() else "",
        "enabled": settings["news_email_enabled"],
        "last_sent": settings["news_emailed_on"],
        "rule": rule_for(ACTION),
    }


@router.post("/api/news-email/send")
async def news_email_send() -> dict:
    """Send the top 5 now (your click is the OK)."""
    from junior.mailer import MailError
    from junior.news.mail import send_news_email

    try:
        return {"message": await send_news_email(by_you=True)}
    except MailError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/api/news-sources")
def news_sources() -> dict:
    sources = load_sources()
    return {
        topic: [{"name": s.name, "kind": s.kind, "url": s.url} for s in sources if s.topic == topic]
        for topic in TOPICS
    } | {"rankings": bool(get_settings().artificial_analysis_api_key)}
