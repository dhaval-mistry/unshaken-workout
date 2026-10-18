# ruff: noqa: E501
"""FastAPI application factory and HTTP middleware configuration."""

import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes.catalog import router as catalog_router
from app.api.routes.exercises import router as exercises_router
from app.api.routes.health import router as health_router
from app.api.routes.plans import router as plans_router
from app.api.routes.profile_custom import router as profile_custom_router
from app.api.routes.sessions import router as sessions_router
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

    app = FastAPI(
        title="Unshaken API",
        version="0.2.0",
        description="""Plan and log private workouts using custom or ExerciseDB exercises.

### Common API journeys
1. **Create a plan:** get options, browse the unified catalog, create a plan, then add exercises and sets. Send each returned `ETag` as `If-Match` on the next mutation.
2. **Start from a plan:** check the current workout, start a session from a plan, record sets, then finish.
3. **Ad hoc workout:** start an empty session, browse and add exercises and sets, then finish or permanently cancel it.
4. **Previous performance:** query latest performance with exactly one exercise source. A null item means no finished history.
5. **Provider outage:** saved snapshots remain readable; catalog browsing can return custom and previously selected external exercises as degraded results.

Local development uses a configured seeded identity. Staging and production fail closed until authentication is implemented.""",
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.settings = runtime_settings
    app.state.exercise_catalog = exercise_catalog
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "If-Match", "X-Correlation-ID"],
        expose_headers=["ETag", "Location"],
    )

    @app.exception_handler(HTTPException)
    async def http_problem(_: Request, error: HTTPException) -> JSONResponse:
        if isinstance(error.detail, dict) and "code" in error.detail:
            content = error.detail
        else:
            # Preserve existing public catalog errors while private APIs use problem details.
            content = {"detail": error.detail}
        return JSONResponse(status_code=error.status_code, content=content, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_problem(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(part) for part in issue["loc"][1:]) for issue in error.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "fields": fields,
            },
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
    app.include_router(catalog_router)
    app.include_router(profile_custom_router)
    app.include_router(plans_router)
    app.include_router(sessions_router)

    def documented_openapi() -> dict[str, object]:
        """Fill shared documentation guarantees consistently across every operation."""
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["tags"] = [
            {"name": name, "description": description}
            for name, description in {
                "health": "Process liveness and PostgreSQL readiness.",
                "exercise catalog": "Unified private and live selectable exercises.",
                "ExerciseDB": "Live provider-specific ExerciseDB operations.",
                "exercise options": "Stable Unshaken taxonomy options.",
                "Profile": "Current user's display preferences.",
                "Custom exercises": "Private user-created exercises.",
                "workout plans": "Reusable ordered workout plans.",
                "workout sessions": "Active and historical performed workouts.",
                "exercise performance": "Latest finished performance snapshots.",
            }.items()
        ]
        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "patch", "put", "delete"}:
                    continue
                stable_name = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")
                operation["operationId"] = f"{method}_{stable_name}"
                operation.setdefault("summary", operation["operationId"].replace("_", " ").title())
                operation.setdefault(
                    "description", f"Use this endpoint to {operation['summary'].lower()}."
                )
                if path.startswith("/api/workout-plans"):
                    operation["description"] += (
                        " Archived plans are read-only. Mutations use the latest ETag in If-Match; "
                        "exercise snapshots may come from a private custom exercise or ExerciseDB."
                    )
                if path.startswith("/api/workout-sessions"):
                    operation["description"] += (
                        " Session mutations use the latest ETag in If-Match. Sets use reps or duration, "
                        "default rest is 120 seconds, and finished or abandoned sessions are immutable. "
                        "Cancellation permanently deletes an active workout; abandonment retains it."
                    )
                for parameter in operation.get("parameters", []):
                    parameter.setdefault("description", f"Value for {parameter['name']}.")
                for response in operation.get("responses", {}).values():
                    headers = response.setdefault("headers", {})
                    headers.setdefault(
                        "X-Correlation-ID",
                        {
                            "description": "Request correlation identifier.",
                            "schema": {"type": "string"},
                        },
                    )
                    if path.startswith(("/api/workout-plans", "/api/workout-sessions")):
                        headers.setdefault(
                            "ETag",
                            {
                                "description": "Current resource version.",
                                "schema": {"type": "string"},
                            },
                        )
                    if response.get("description") == "Successful Response" and method == "post":
                        headers.setdefault(
                            "Location",
                            {"description": "Created resource path.", "schema": {"type": "string"}},
                        )
                for error_status in ("422", "503"):
                    operation.setdefault("responses", {}).setdefault(
                        error_status,
                        {
                            "description": "Safe error response.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ProblemResponse"}
                                }
                            },
                        },
                    )
        for model in schema.get("components", {}).get("schemas", {}).values():
            for field_name, field in model.get("properties", {}).items():
                field.setdefault("description", f"Value for {field_name.replace('_', ' ')}.")
        app.openapi_schema = schema
        return schema

    app.openapi = documented_openapi  # type: ignore[method-assign]
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
