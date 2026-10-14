"""FastAPI app. Run with: uvicorn junior.main:app --reload"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from junior import __version__
from junior.config import get_settings
from junior.db import init_db
from junior.logging_setup import setup_logging
from junior.models import get_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    get_router()  # a broken agents/models.toml stops startup with a clear error
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Junior Muneer", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    log.info("Junior Muneer backend %s ready", __version__)
    return app


app = create_app()
