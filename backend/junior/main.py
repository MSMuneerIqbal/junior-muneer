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
from junior.chat.api import router as chat_router
from junior.chat.service import ChatService
from junior.config import get_settings
from junior.costs import router as costs_router
from junior.db import init_db
from junior.logging_setup import setup_logging
from junior.memories import router as memories_router
from junior.models import get_router
from junior.pause import router as pause_router
from junior.permissions import router as permissions_router
from junior.playbooks import load_playbooks
from junior.playbooks import router as playbooks_router
from junior.profile import router as profile_router
from junior.registry import load_registry
from junior.scheduler import scheduler_loop
from junior.settings_api import router as settings_router
from junior.voice import FakeVoice, OpenAIVoice, VoiceClient
from junior.voice import router as voice_router

log = logging.getLogger(__name__)


def create_app(
    model_provider: Callable[[], ModelProvider] | None = None,
    voice: Callable[[], VoiceClient] | None = None,
    realtime: Callable[[], RealtimeGateway] | None = None,
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
        # A broken agents/models.toml, agent file or playbook stops startup with a clear error.
        get_router()
        app.state.registry = load_registry()
        app.state.playbooks = load_playbooks()
        app.state.chat = ChatService(app.state.registry, model_provider)
        app.state.voice = voice
        app.state.calls = CallManager(realtime, app.state.registry, model_provider)
        scheduler = (
            asyncio.create_task(scheduler_loop()) if get_settings().scheduler_enabled else None
        )
        log.info("Junior Muneer backend %s ready", __version__)
        yield
        if scheduler:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler

    app = FastAPI(title="Junior Muneer", version=__version__, lifespan=lifespan)
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
    app.include_router(profile_router)
    app.include_router(playbooks_router)
    app.include_router(permissions_router)
    app.include_router(approvals_router)
    return app


app = create_app()
