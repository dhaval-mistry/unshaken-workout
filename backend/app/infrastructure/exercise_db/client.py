"""Typed, live-only adapter for the configured ExerciseDB subscription."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx


class ExerciseCatalogUnavailableError(Exception):
    """Raised when the catalog cannot be safely served to an API consumer."""

    def __init__(self, reason: str, retry_after: str | None = None) -> None:
        self.reason = reason
        self.retry_after = retry_after
        super().__init__(reason)


class ExerciseNotFoundError(Exception):
    """Raised only when the configured provider confirms an unknown exercise identifier."""


@dataclass(frozen=True)
class NormalizedExercise:
    """Provider-independent exercise content returned without persisting provider data."""

    id: str
    name: str
    body_parts: list[str]
    target_muscles: list[str]
    equipment: list[str]
    exercise_type: str | None
    instructions: list[str]
    media_url: str | None


@dataclass(frozen=True)
class ExerciseSearchResult:
    """A page of normalized content fetched for the current request only."""

    items: list[NormalizedExercise]
    total: int | None


class ExerciseCatalog(Protocol):
    """Boundary keeping provider transport and payload details out of routes."""

    async def search(
        self,
        *,
        query: str | None,
        body_part: str | None,
        equipment: str | None,
        exercise_type: str | None,
        limit: int,
        offset: int,
    ) -> ExerciseSearchResult: ...

    async def get_by_id(self, exercise_id: str) -> NormalizedExercise: ...


def _string_list(value: Any) -> list[str]:
    """Normalize current and legacy provider scalar/list shapes without leaking them upward."""

    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_exercise(payload: object, *, allow_media: bool) -> NormalizedExercise:
    """Translate supported ExerciseDB response shapes into the application's stable contract."""

    if not isinstance(payload, dict):
        raise ExerciseCatalogUnavailableError("invalid_response")

    exercise_id = _optional_string(payload.get("exerciseId") or payload.get("id"))
    name = _optional_string(payload.get("name"))
    if exercise_id is None or name is None:
        raise ExerciseCatalogUnavailableError("invalid_response")

    media = _optional_string(payload.get("gifUrl") or payload.get("imageUrl"))
    return NormalizedExercise(
        id=exercise_id,
        name=name,
        body_parts=_string_list(payload.get("bodyParts") or payload.get("bodyPart")),
        target_muscles=_string_list(payload.get("targetMuscles") or payload.get("target")),
        equipment=_string_list(payload.get("equipments") or payload.get("equipment")),
        exercise_type=_optional_string(payload.get("exerciseType")),
        instructions=_string_list(payload.get("instructions")),
        # Provider media is referenced only with display permission; never fetched or stored.
        media_url=media if allow_media else None,
    )


class ExerciseDbClient:
    """Calls ExerciseDB at request time with no cache or database dependency."""

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        host: str | None,
        allow_media: bool,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._api_key = api_key
        self._host = host
        self._allow_media = allow_media
        self._transport = transport

    def _configured(self) -> bool:
        return self._base_url is not None and self._api_key is not None and self._host is not None

    def _headers(self) -> dict[str, str]:
        assert self._api_key is not None
        assert self._host is not None
        return {"X-RapidAPI-Key": self._api_key, "X-RapidAPI-Host": self._host}

    async def _request(self, path: str, params: dict[str, str | int]) -> httpx.Response:
        if not self._configured():
            raise ExerciseCatalogUnavailableError("not_configured")
        assert self._base_url is not None
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0), transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}{path}", params=params, headers=self._headers()
                )
        except httpx.TimeoutException as error:
            raise ExerciseCatalogUnavailableError("timeout") from error
        except httpx.HTTPError as error:
            raise ExerciseCatalogUnavailableError("connection_failed") from error
        if response.status_code == 404:
            raise ExerciseNotFoundError()
        if response.status_code == 429:
            raise ExerciseCatalogUnavailableError(
                "rate_limited", response.headers.get("Retry-After")
            )
        if response.is_error:
            raise ExerciseCatalogUnavailableError("provider_error")
        return response

    async def search(
        self,
        *,
        query: str | None,
        body_part: str | None,
        equipment: str | None,
        exercise_type: str | None,
        limit: int,
        offset: int,
    ) -> ExerciseSearchResult:
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        for key, value in {
            "name": query,
            "bodyPart": body_part,
            "equipment": equipment,
            "exerciseType": exercise_type,
        }.items():
            if value:
                params[key] = value
        response = await self._request("/exercises", params)
        try:
            body: object = response.json()
        except ValueError as error:
            raise ExerciseCatalogUnavailableError("invalid_response") from error
        items_payload = body.get("data", []) if isinstance(body, dict) else body
        if not isinstance(items_payload, list):
            raise ExerciseCatalogUnavailableError("invalid_response")
        total_value = (
            body.get("total") if isinstance(body, dict) else response.headers.get("X-Total-Count")
        )
        total = (
            int(total_value)
            if isinstance(total_value, int | str) and str(total_value).isdigit()
            else None
        )
        return ExerciseSearchResult(
            items=[
                normalize_exercise(item, allow_media=self._allow_media) for item in items_payload
            ],
            total=total,
        )

    async def get_by_id(self, exercise_id: str) -> NormalizedExercise:
        response = await self._request(f"/exercises/exercise/{quote(exercise_id, safe='')}", {})
        try:
            return normalize_exercise(response.json(), allow_media=self._allow_media)
        except ValueError as error:
            raise ExerciseCatalogUnavailableError("invalid_response") from error
