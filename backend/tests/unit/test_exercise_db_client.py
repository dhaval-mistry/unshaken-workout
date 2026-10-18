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
        assert request.url.path == "/exercises/name/press"
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "20"
        assert request.headers["X-RapidAPI-Key"] == "test-key"
        assert request.headers["X-RapidAPI-Host"] == "provider.example"
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
        query="press",
        body_part=None,
        equipment=None,
        target=None,
        exercise_type=None,
        limit=20,
        offset=20,
    )

    assert result.total == 1
    assert result.items[0].name == "Supported row"


@pytest.mark.asyncio
async def test_unconfigured_catalog_returns_safe_configuration_category() -> None:
    client = ExerciseDbClient(base_url=None, api_key=None, host=None, allow_media=False)

    with pytest.raises(ExerciseCatalogUnavailableError, match="not_configured"):
        await client.search(
            query=None,
            body_part=None,
            equipment=None,
            target=None,
            exercise_type=None,
            limit=20,
            offset=0,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "path"),
    [
        ({}, "/exercises"),
        ({"body_part": "upper arms"}, "/exercises/bodyPart/upper%20arms"),
        ({"equipment": "body weight"}, "/exercises/equipment/body%20weight"),
        ({"target": "upper back"}, "/exercises/target/upper%20back"),
    ],
)
async def test_search_uses_documented_provider_path(filters: dict[str, str], path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.decode().split("?", 1)[0] == path
        assert "name" not in request.url.params
        return httpx.Response(200, json=[])

    client = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=httpx.MockTransport(handler),
    )
    result = await client.search(
        query=filters.get("query"),
        body_part=filters.get("body_part"),
        equipment=filters.get("equipment"),
        target=filters.get("target"),
        exercise_type=None,
        limit=10,
        offset=0,
    )
    assert result.items == []


@pytest.mark.asyncio
async def test_taxonomy_status_and_media_are_live_and_validated() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/status":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/image/0001":
            return httpx.Response(200, content=b"GIF89a", headers={"Content-Type": "image/gif"})
        return httpx.Response(200, json=["chest", "back"])

    client = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=True,
        transport=httpx.MockTransport(handler),
    )
    assert await client.status() is True
    assert await client.list_values("body_parts") == ["chest", "back"]
    assert await client.list_values("targets") == ["chest", "back"]
    assert await client.list_values("equipment") == ["chest", "back"]
    assert await client.get_image("0001") == (b"GIF89a", "image/gif")
    assert paths == [
        "/status",
        "/exercises/bodyPartList",
        "/exercises/targetList",
        "/exercises/equipmentList",
        "/image/0001",
    ]


@pytest.mark.asyncio
async def test_media_is_disabled_by_default_and_rejects_non_images() -> None:
    disabled = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    with pytest.raises(ExerciseCatalogUnavailableError, match="media_not_enabled"):
        await disabled.get_image("0001")

    enabled = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"oops", headers={"Content-Type": "text/html"}
            )
        ),
    )
    with pytest.raises(ExerciseCatalogUnavailableError, match="invalid_response"):
        await enabled.get_image("0001")


@pytest.mark.asyncio
async def test_rate_limit_and_timeout_are_safe_failures() -> None:
    limited = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "30"})
        ),
    )
    with pytest.raises(ExerciseCatalogUnavailableError, match="rate_limited") as error:
        await limited.list_values("targets")
    assert error.value.retry_after == "30"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private transport detail")

    unavailable = ExerciseDbClient(
        base_url="https://provider.example",
        api_key="test-key",
        host="provider.example",
        allow_media=False,
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ExerciseCatalogUnavailableError, match="timeout") as error:
        await unavailable.status()
    assert "private transport detail" not in str(error.value)
