"""API route tests use a fake catalog, keeping external calls out of route validation."""

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.infrastructure.exercise_db.client import (
    ExerciseCatalogUnavailableError,
    ExerciseNotFoundError,
    ExerciseSearchResult,
    NormalizedExercise,
)
from app.main import create_app


class CatalogStub:
    def __init__(self) -> None:
        self.search_error: Exception | None = None
        self.detail_error: Exception | None = None
        self.last_search: dict[str, object] | None = None

    async def search(self, **kwargs: object) -> ExerciseSearchResult:
        self.last_search = kwargs
        if self.search_error:
            raise self.search_error
        return ExerciseSearchResult(items=[self._exercise()], total=1)

    async def get_by_id(self, exercise_id: str) -> NormalizedExercise:
        if self.detail_error:
            raise self.detail_error
        assert exercise_id == "exr_123"
        return self._exercise()

    @staticmethod
    def _exercise() -> NormalizedExercise:
        return NormalizedExercise(
            id="exr_123",
            name="Supported row",
            body_parts=["chest"],
            target_muscles=["pectorals"],
            equipment=["barbell"],
            exercise_type="strength",
            instructions=["Set up"],
            media_url=None,
        )


def build_client(stub: CatalogStub) -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test"))
    app.state.exercise_catalog = stub
    return TestClient(app)


def test_catalog_returns_normalized_page_and_bounded_query() -> None:
    stub = CatalogStub()
    with build_client(stub) as client:
        response = client.get("/api/exercises?query=press&page=2&page_size=20")

    assert response.status_code == 200
    assert response.json()["items"][0]["source"]["name"] == "ExerciseDB"
    assert stub.last_search == {
        "query": "press",
        "body_part": None,
        "equipment": None,
        "exercise_type": None,
        "limit": 20,
        "offset": 20,
    }


def test_catalog_returns_safe_error_when_provider_is_not_configured() -> None:
    stub = CatalogStub()
    stub.search_error = ExerciseCatalogUnavailableError("not_configured")
    with build_client(stub) as client:
        response = client.get("/api/exercises")

    assert response.status_code == 503
    assert response.json() == {
        "code": "catalog_unavailable",
        "message": "The standard exercise catalog is temporarily unavailable. Please try again.",
    }


def test_detail_distinguishes_not_found_from_provider_failure() -> None:
    missing = CatalogStub()
    missing.detail_error = ExerciseNotFoundError()
    with build_client(missing) as client:
        missing_response = client.get("/api/exercises/missing")

    unavailable = CatalogStub()
    unavailable.detail_error = ExerciseCatalogUnavailableError("provider_error")
    with build_client(unavailable) as client:
        unavailable_response = client.get("/api/exercises/exr_123")

    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Exercise not found."}
    assert unavailable_response.status_code == 503
    assert unavailable_response.json()["code"] == "catalog_unavailable"


def test_catalog_rejects_unbounded_page_size_and_invalid_detail_identifier() -> None:
    with build_client(CatalogStub()) as client:
        page_response = client.get("/api/exercises?page_size=51")
        id_response = client.get("/api/exercises/bad.id")

    assert page_response.status_code == 422
    assert id_response.status_code == 422
