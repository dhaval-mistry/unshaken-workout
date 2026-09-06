from fastapi.testclient import TestClient

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
