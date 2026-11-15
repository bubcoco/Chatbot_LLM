"""FastAPI app factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel

from supportkit.api import chat
from supportkit.bootstrap import open_runtime
from supportkit.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, model: BaseChatModel | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with open_runtime(
            settings.database_url, settings.supportkit_model, model=model
        ) as rt:
            app.state.runtime = rt
            app.state.thread_locks = {}
            yield

    demo = settings.supportkit_demo_mode
    if demo:
        app = FastAPI(title="supportkit", lifespan=lifespan)
    else:
        app = FastAPI(
            title="supportkit",
            lifespan=lifespan,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "model": settings.supportkit_model,
            "demo_mode": settings.supportkit_demo_mode,
        }

    if demo:
        app.include_router(chat.router)
        logger.warning(
            "DEMO MODE: /chat trusts X-Demo-* identity headers. Do not expose this server."
        )
    return app
