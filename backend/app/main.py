"""FastAPI application factory and HTTP middleware configuration."""

import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes.health import router as health_router
from app.core.logging import configure_logging
from app.core.request_context import set_correlation_id
from app.core.settings import Settings, get_settings
from app.infrastructure.db.database import Database

logger = logging.getLogger(__name__)
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _correlation_id(request: Request) -> str:
    """Reuse a bounded client identifier or create one to prevent log injection."""

    incoming = request.headers.get("X-Correlation-ID")
    if incoming and _CORRELATION_ID_PATTERN.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with injectable settings for tests and future deployment hosts."""

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    database = Database(str(runtime_settings.database_url))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await database.dispose()

    app = FastAPI(title="Unshaken API", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next: object) -> Response:
        """Attach correlation IDs to each response and request-scoped structured log record."""

        correlation_id = _correlation_id(request)
        set_correlation_id(correlation_id)
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info("request_completed", extra={"method": request.method, "path": request.url.path})
        return response

    app.include_router(health_router)
    return app


app = create_app()
