"""Adapter tests keep ExerciseDB payload and transport concerns out of HTTP routes."""

import httpx
import pytest

from app.infrastructure.exercise_db.client import (
    ExerciseCatalogUnavailableError,
    ExerciseDbClient,
    ExerciseNotFoundError,
    normalize_exercise,
)


def _transport(handler: httpx.MockTransport) -> httpx.MockTransport:
    return handler


def test_normalize_exercise_supports_current_provider_lists_and_hides_media_by_default() -> None:
    exercise = normalize_exercise(
        {
            "exerciseId": "exr_123",
            "name": "Supported row",
            "bodyParts": ["chest"],
            "targetMuscles": ["pectorals"],
            "equipments": ["barbell"],
            "exerciseType": "strength",
            "instructions": ["Set up", "Move"],
            "gifUrl": "https://provider.example/media.gif",
        },
        allow_media=False,
    )

    assert exercise.id == "exr_123"
    assert exercise.body_parts == ["chest"]
    assert exercise.instructions == ["Set up", "Move"]
    assert exercise.media_url is None


@pytest.mark.asyncio
async def test_search_normalizes_provider_response_and_sends_bounded_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/exercises"
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "20"
        assert request.url.params["name"] == "press"
        assert request.headers["X-RapidAPI-Key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "exerciseId": "exr_123",
                        "name": "Supported row",
                        "bodyParts": ["chest"],
                        "targetMuscles": ["pectorals"],
                        "equipments": ["barbell"],
                    }
                ],
                "total": 1,
            },
        )

    client = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=_transport(httpx.MockTransport(handler)),
    )

    result = await client.search(
        query="press", body_part=None, equipment=None, exercise_type=None, limit=20, offset=20
    )

    assert result.total == 1
    assert result.items[0].name == "Supported row"


@pytest.mark.asyncio
async def test_unconfigured_catalog_returns_safe_configuration_category() -> None:
    client = ExerciseDbClient(base_url=None, api_key=None, host=None, allow_media=False)

    with pytest.raises(ExerciseCatalogUnavailableError, match="not_configured"):
        await client.search(
            query=None, body_part=None, equipment=None, exercise_type=None, limit=20, offset=0
        )


@pytest.mark.asyncio
async def test_provider_failure_never_exposes_raw_response_body() -> None:
    client = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=_transport(
            httpx.MockTransport(lambda request: httpx.Response(500, text="provider-secret-body"))
        ),
    )

    with pytest.raises(ExerciseCatalogUnavailableError, match="provider_error") as error:
        await client.get_by_id("exr_123")

    assert "provider-secret-body" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_not_found_is_distinct_from_temporary_failure() -> None:
    client = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=_transport(httpx.MockTransport(lambda request: httpx.Response(404))),
    )

    with pytest.raises(ExerciseNotFoundError):
        await client.get_by_id("missing")
