import io
import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.core.settings import Settings
from app.main import create_app


def build_client() -> TestClient:
    settings = Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")
    return TestClient(create_app(settings))


def test_liveness_returns_ok_and_correlation_identifier() -> None:
    with build_client() as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "client-request.42"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Correlation-ID"] == "client-request.42"


def test_liveness_replaces_invalid_correlation_identifier() -> None:
    with build_client() as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "invalid\nvalue"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] != "invalid\nvalue"


def test_safe_access_log_omits_query_string_secret() -> None:
    """Exercise the ASGI stack and inspect its actual structured access event."""

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    secret = "validation-secret-value"
    app = create_app(Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test"))
    app_logger = logging.getLogger("app.main")
    original_disabled = app_logger.disabled
    original_propagate = app_logger.propagate
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.disabled = False
    app_logger.propagate = False

    try:
        with TestClient(app) as client:
            response = client.get(f"/health/live?access_token={secret}")
    finally:
        app_logger.removeHandler(handler)
        app_logger.disabled = original_disabled
        app_logger.propagate = original_propagate

    output = stream.getvalue()
    assert response.status_code == 200
    assert secret not in output
    payload = json.loads(output)
    assert payload["message"] == "http_request_completed"
    assert payload["path"] == "/health/live"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
    assert "duration_ms" in payload


def test_readiness_returns_service_unavailable_when_database_is_down() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test"))

    async def unavailable() -> bool:
        return False

    app.state.database.check_connection = unavailable
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_readiness_returns_ok_when_database_accepts_probe() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test"))

    async def available() -> bool:
        return True

    app.state.database.check_connection = available
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
