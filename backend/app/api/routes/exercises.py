"""Read-only, normalized routes for the configured live ExerciseDB catalog."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.infrastructure.exercise_db.client import (
    ExerciseCatalog,
    ExerciseCatalogUnavailableError,
    ExerciseNotFoundError,
    NormalizedExercise,
)

router = APIRouter(prefix="/api/exercises", tags=["exercises"])
_EXERCISE_ID = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,100}$")]


class ExerciseSource(BaseModel):
    """Required attribution supplied alongside every live provider record."""

    name: Literal["ExerciseDB"] = "ExerciseDB"
    notice: str = "Exercise data is provided live by ExerciseDB."


class ExerciseResponse(BaseModel):
    """Stable public model that deliberately omits provider URLs and credential details."""

    id: str
    name: str
    body_parts: list[str]
    target_muscles: list[str]
    equipment: list[str]
    exercise_type: str | None
    instructions: list[str]
    media_url: str | None
    source: ExerciseSource = Field(default_factory=ExerciseSource)


class ExercisePageResponse(BaseModel):
    """Bounded catalog page returned from a current provider request."""

    items: list[ExerciseResponse]
    page: int
    page_size: int
    total: int | None


class CatalogProblem(BaseModel):
    """Safe error shape for absent configuration and transient provider failures."""

    code: Literal["catalog_unavailable"]
    message: str


def _response(exercise: NormalizedExercise) -> ExerciseResponse:
    return ExerciseResponse(
        id=exercise.id,
        name=exercise.name,
        body_parts=exercise.body_parts,
        target_muscles=exercise.target_muscles,
        equipment=exercise.equipment,
        exercise_type=exercise.exercise_type,
        instructions=exercise.instructions,
        media_url=exercise.media_url,
    )


def _unavailable(error: ExerciseCatalogUnavailableError) -> JSONResponse:
    """Map provider failures without passing through raw errors, URLs, or response bodies."""

    headers = (
        {"Retry-After": error.retry_after}
        if error.retry_after and error.reason == "rate_limited"
        else {}
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=CatalogProblem(
            code="catalog_unavailable",
            message="The standard exercise catalog is temporarily unavailable. Please try again.",
        ).model_dump(),
        headers=headers,
    )


def _catalog(request: Request) -> ExerciseCatalog:
    return cast(ExerciseCatalog, request.app.state.exercise_catalog)


@router.get("", response_model=ExercisePageResponse, responses={503: {"model": CatalogProblem}})
async def list_exercises(
    request: Request,
    query: Annotated[str | None, Query(max_length=100)] = None,
    body_part: Annotated[str | None, Query(max_length=60)] = None,
    equipment: Annotated[str | None, Query(max_length=60)] = None,
    exercise_type: Annotated[str | None, Query(max_length=60)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    """Browse one bounded live page; no provider content is cached or persisted."""

    try:
        result = await _catalog(request).search(
            query=query,
            body_part=body_part,
            equipment=equipment,
            exercise_type=exercise_type,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return ExercisePageResponse(
        items=[_response(item) for item in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.get(
    "/{exercise_id}", response_model=ExerciseResponse, responses={503: {"model": CatalogProblem}}
)
async def get_exercise(
    request: Request, exercise_id: _EXERCISE_ID
) -> ExerciseResponse | JSONResponse:
    """Retrieve one provider identifier through the fixed adapter endpoint, never a client URL."""

    try:
        exercise = await _catalog(request).get_by_id(exercise_id)
    except ExerciseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found."
        ) from error
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return _response(exercise)
