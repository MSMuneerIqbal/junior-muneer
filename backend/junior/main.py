"""FastAPI app. Run with: uvicorn junior.main:app --reload"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from junior import __version__
from junior.agent.builder import ModelProvider, openai_model_provider
from junior.agent.fake import fake_model_provider
from junior.approvals import router as approvals_router
from junior.audit import router as audit_router
from junior.backup import router as backup_router
from junior.calls import CallManager, OpenAIRealtime, RealtimeGateway
from junior.calls import router as calls_router
from junior.gemini_live import router as gemini_router
from junior.chat.api import router as chat_router
from junior.chat.service import ChatService
from junior.config import get_settings
from junior.costs import router as costs_router
from junior.db import init_db
from junior.logging_setup import setup_logging
from junior.freelance.jobs import router as jobs_router
from junior.freelance.orders import router as orders_router
from junior.github.oauth import router as github_router
from junior.files import router as files_router
from junior.inbox import router as inbox_router
from junior.google.auth import router as google_router
from junior.ideas import router as ideas_router
from junior.images import router as images_router
from junior.memories import router as memories_router
from junior.models import get_router
from junior.pause import router as pause_router
from junior.news.api import router as news_router
from junior.news.digest import morning_digests
from junior.news.sources import load_sources
from junior.permissions import router as permissions_router
from junior.playbooks import load_playbooks
from junior.playbooks import router as playbooks_router
from junior.skills import router as skills_router
from junior.profile import router as profile_router
from junior.registry import load_registry
from junior.scheduler import scheduler_loop
from junior.senders.api import router as senders_router
from junior.senders.dispatch import recover_interrupted_sends
from junior.background import recover_interrupted as recover_background
from junior.background import router as tasks_router
from junior.reports import morning_briefing
from junior.memory_tidy import weekly_tidy
from junior.feeds import feeds_if_due
from junior.feeds import router as feeds_router
from junior.whatsapp import router as whatsapp_router
from junior.computer.api import router as computer_router
from junior.hosts import LocalOnly
from junior.reports import router as reports_router
from junior.senders.registry import SenderRegistry, set_current
from junior.settings_api import router as settings_router
from junior.voice import FakeVoice, OpenAIVoice, VoiceClient, engine_voice
from junior.voice import router as voice_router

log = logging.getLogger(__name__)


def default_senders(settings) -> SenderRegistry:
    """The connected API senders. FAKE_AI: a fake Facebook Page, so posting can be tried safely."""
    registry = SenderRegistry()
    if settings.meta_page_id and settings.meta_page_token:
        from junior.senders.facebook import FacebookPageSender

        registry.add(
            FacebookPageSender(settings.meta_page_id, settings.meta_page_token, settings.meta_app_secret, settings.meta_graph_version)
        )
    from junior.senders.gmail import GmailSender

    registry.add(GmailSender())  # sends only when Google is connected with Gmail drafts allowed
    from junior.computer.sender import ComputerSender

    registry.add(ComputerSender())  # approved file changes and commands on this PC (Phase 9)
    if settings.fake_ai and not registry.for_action("facebook.page.post"):
        from junior.senders.fake import FakeSender

        registry.add(FakeSender())
    return registry


def create_app(
    model_provider: Callable[[], ModelProvider] | None = None,
    voice: Callable[[], VoiceClient] | None = None,
    realtime: Callable[[], RealtimeGateway] | None = None,
    senders: Callable[[], SenderRegistry] | None = None,
) -> FastAPI:
    """The app. Tests pass a fake model_provider and voice so no real AI is called."""
    settings = get_settings()
    setup_logging(settings.log_level)
    if model_provider is None:
        model_provider = fake_model_provider if settings.fake_ai else openai_model_provider
        if settings.fake_ai:
            log.warning("FAKE_AI is on: answers are fake echoes, not real AI.")
    if voice is None:
        voice = FakeVoice if settings.fake_ai else OpenAIVoice
    if realtime is None:
        realtime = OpenAIRealtime  # live calls need the real API, even with FAKE_AI

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db()
        # A broken agents/models.toml, agent file, playbook or news/sources.toml stops startup with a clear error.
        get_router()
        app.state.registry = load_registry()
        app.state.playbooks = load_playbooks()
        from junior.skills import load_skills

        app.state.skills = load_skills()  # a broken skill file stops startup with a clear error
        app.state.news_sources = load_sources()
        app.state.senders = senders() if senders is not None else default_senders(settings)
        recover_interrupted_sends()
        recover_background()
        set_current(app.state.senders)
        app.state.chat = ChatService(app.state.registry, model_provider)
        app.state.openai_voice = voice
        app.state.voice = engine_voice(voice)  # OpenAI or Gemini, as Settings -> Voice says
        app.state.calls = CallManager(realtime, app.state.registry, model_provider)
        from junior.whatsapp import resume_unanswered

        resume_unanswered(app)  # WhatsApp messages a restart cut off get their answer now
        async def news_job() -> None:
            from junior.news.mail import daily_news_email

            await morning_digests(app.state.registry, model_provider)
            await daily_news_email()

        async def briefing_job() -> None:
            await morning_briefing(app.state.registry, model_provider)

        async def tidy_job() -> None:
            await weekly_tidy(app.state.registry, model_provider)

        async def email_job() -> None:
            from junior.inbox import check_inbox

            await check_inbox(app.state.registry, model_provider)

        scheduler = (
            asyncio.create_task(scheduler_loop(extra=[("morning news", news_job), ("morning briefing", briefing_job), ("memory tidy-up", tidy_job), ("your feeds", feeds_if_due), ("email watcher", email_job)]))
            if get_settings().scheduler_enabled
            else None
        )
        log.info("Junior Muneer backend %s ready", __version__)
        yield
        if scheduler:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler

    app = FastAPI(title="Junior Muneer", version=__version__, lifespan=lifespan)
    app.add_middleware(LocalOnly)  # only the WhatsApp webhook answers to outside addresses
    app.add_middleware(
        CORSMiddleware,
        # The dashboard may be opened as localhost or 127.0.0.1.
        allow_origins=sorted(
            {settings.frontend_origin, settings.frontend_origin.replace("localhost", "127.0.0.1")}
        ),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(chat_router)
    app.include_router(memories_router)
    app.include_router(costs_router)
    app.include_router(audit_router)
    app.include_router(pause_router)
    app.include_router(backup_router)
    app.include_router(settings_router)
    app.include_router(voice_router)
    app.include_router(calls_router)
    app.include_router(gemini_router)
    app.include_router(profile_router)
    app.include_router(playbooks_router)
    app.include_router(skills_router)
    app.include_router(permissions_router)
    app.include_router(approvals_router)
    app.include_router(news_router)
    app.include_router(senders_router)
    app.include_router(ideas_router)
    app.include_router(jobs_router)
    app.include_router(orders_router)
    app.include_router(github_router)
    app.include_router(google_router)
    app.include_router(files_router)
    app.include_router(inbox_router)
    app.include_router(tasks_router)
    app.include_router(reports_router)
    app.include_router(feeds_router)
    app.include_router(whatsapp_router)
    app.include_router(computer_router)
    app.include_router(images_router)
    return app


app = create_app()
