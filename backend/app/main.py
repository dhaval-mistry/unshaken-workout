"""FastAPI application factory and HTTP middleware configuration."""

import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes.exercises import router as exercises_router
from app.api.routes.health import router as health_router
from app.core.logging import configure_logging
from app.core.request_context import set_correlation_id
from app.core.settings import Settings, get_settings
from app.infrastructure.db.database import Database
from app.infrastructure.exercise_db.client import ExerciseDbClient

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
    app_exercise_key = (
        runtime_settings.exercise_db_api_key.get_secret_value()
        if runtime_settings.exercise_db_api_key is not None
        else None
    )
    exercise_catalog = ExerciseDbClient(
        base_url=str(runtime_settings.exercise_db_base_url)
        if runtime_settings.exercise_db_base_url
        else None,
        api_key=app_exercise_key,
        host=runtime_settings.exercise_db_host,
        allow_media=runtime_settings.exercise_db_media_enabled,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await database.dispose()

    app = FastAPI(title="Unshaken API", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.state.exercise_catalog = exercise_catalog
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Attach correlation IDs and record a query-free access event for each request."""

        correlation_id = _correlation_id(request)
        set_correlation_id(correlation_id)
        started_at = perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        # Uvicorn access logging is disabled because it records raw query strings.
        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    app.include_router(health_router)
    app.include_router(exercises_router)
    return app


def _configuration_failure_app() -> FastAPI:
    """Start safely when malformed settings must not expose supplied values."""

    app = FastAPI(title="Unshaken API", version="0.1.0")

    @app.get("/{path:path}")
    async def configuration_unavailable(path: str) -> JSONResponse:
        del path
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": "configuration_unavailable",
                "message": "Service configuration is unavailable.",
            },
        )

    return app


try:
    app = create_app()
except ValidationError as error:
    # ValidationError text can contain submitted settings values, so record field names only.
    configure_logging("ERROR")
    logger.error(
        "configuration_invalid",
        extra={
            "invalid_fields": [
                ".".join(str(part) for part in issue["loc"]) for issue in error.errors()
            ]
        },
    )
    app = _configuration_failure_app()
