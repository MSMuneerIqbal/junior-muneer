"""FastAPI app. Run with: uvicorn junior.main:app --reload"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from junior import __version__
from junior.config import get_settings
from junior.logging_setup import setup_logging

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Junior Muneer", version=__version__)
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
