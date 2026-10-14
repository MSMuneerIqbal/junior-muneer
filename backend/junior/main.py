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
from junior.audit import router as audit_router
from junior.backup import router as backup_router
from junior.chat.api import router as chat_router
from junior.chat.service import ChatService
from junior.config import get_settings
from junior.costs import router as costs_router
from junior.db import init_db
from junior.logging_setup import setup_logging
from junior.memories import router as memories_router
from junior.models import get_router
from junior.pause import router as pause_router
from junior.registry import load_registry
from junior.scheduler import scheduler_loop

log = logging.getLogger(__name__)


def create_app(model_provider: Callable[[], ModelProvider] = openai_model_provider) -> FastAPI:
    """The app. Tests pass a fake model_provider so no real AI is called."""
    settings = get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db()
        # A broken agents/models.toml or agent file stops startup with a clear error.
        get_router()
        app.state.registry = load_registry()
        app.state.chat = ChatService(app.state.registry, model_provider)
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
    return app


app = create_app()
