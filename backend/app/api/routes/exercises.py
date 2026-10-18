"""Read-only, normalized routes for the configured live ExerciseDB catalog."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.infrastructure.exercise_db.client import (
    ExerciseCatalog,
    ExerciseCatalogUnavailableError,
    ExerciseNotFoundError,
    NormalizedExercise,
)

router = APIRouter(prefix="/api/exercises", tags=["ExerciseDB"])
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


class CatalogStatusResponse(BaseModel):
    available: bool


class CatalogValuesResponse(BaseModel):
    items: list[str]


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
    target: Annotated[str | None, Query(max_length=60)] = None,
    exercise_type: Annotated[str | None, Query(max_length=60)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    """Browse one bounded live page; no provider content is cached or persisted."""

    if (
        exercise_type is not None
        or sum(bool(value) for value in (query, body_part, equipment, target)) > 1
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose one supported filter: query, body_part, equipment, or target.",
        )
    try:
        result = await _catalog(request).search(
            query=query,
            body_part=body_part,
            equipment=equipment,
            target=target,
            exercise_type=exercise_type,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    except ExerciseNotFoundError as error:
        raise HTTPException(status_code=404, detail="Filter not found.") from error
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return ExercisePageResponse(
        items=[_response(item) for item in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.get("/status", response_model=CatalogStatusResponse)
async def catalog_status(request: Request) -> CatalogStatusResponse | JSONResponse:
    try:
        await _catalog(request).status()
    except ExerciseNotFoundError:
        return _unavailable(ExerciseCatalogUnavailableError("provider_error"))
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return CatalogStatusResponse(available=True)


@router.get("/body-parts", response_model=CatalogValuesResponse)
async def list_body_parts(request: Request) -> CatalogValuesResponse | JSONResponse:
    return await _values(request, "body_parts")


@router.get("/targets", response_model=CatalogValuesResponse)
async def list_targets(request: Request) -> CatalogValuesResponse | JSONResponse:
    return await _values(request, "targets")


@router.get("/equipment", response_model=CatalogValuesResponse)
async def list_equipment(request: Request) -> CatalogValuesResponse | JSONResponse:
    return await _values(request, "equipment")


async def _values(request: Request, kind: str) -> CatalogValuesResponse | JSONResponse:
    try:
        values = await _catalog(request).list_values(kind)
    except ExerciseNotFoundError:
        return _unavailable(ExerciseCatalogUnavailableError("provider_error"))
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return CatalogValuesResponse(items=values)


async def _filtered(
    request: Request, *, kind: str, value: str, page: int, page_size: int
) -> ExercisePageResponse | JSONResponse:
    filters: dict[str, str | None] = {
        "query": None,
        "body_part": None,
        "equipment": None,
        "target": None,
    }
    filters[kind] = value
    try:
        result = await _catalog(request).search(
            **filters, exercise_type=None, limit=page_size, offset=(page - 1) * page_size
        )
    except ExerciseNotFoundError as error:
        raise HTTPException(status_code=404, detail="Filter not found.") from error
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return ExercisePageResponse(
        items=[_response(item) for item in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.get("/search/{name}", response_model=ExercisePageResponse)
async def search_by_name(
    request: Request,
    name: Annotated[str, Path(min_length=1, max_length=100)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    return await _filtered(request, kind="query", value=name, page=page, page_size=page_size)


@router.get("/target/{target}", response_model=ExercisePageResponse)
async def list_by_target(
    request: Request,
    target: Annotated[str, Path(min_length=1, max_length=60)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    return await _filtered(request, kind="target", value=target, page=page, page_size=page_size)


@router.get("/body-part/{body_part}", response_model=ExercisePageResponse)
async def list_by_body_part(
    request: Request,
    body_part: Annotated[str, Path(min_length=1, max_length=60)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    return await _filtered(
        request, kind="body_part", value=body_part, page=page, page_size=page_size
    )


@router.get("/equipment/{equipment}", response_model=ExercisePageResponse)
async def list_by_equipment(
    request: Request,
    equipment: Annotated[str, Path(min_length=1, max_length=60)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ExercisePageResponse | JSONResponse:
    return await _filtered(
        request, kind="equipment", value=equipment, page=page, page_size=page_size
    )


@router.get("/image/{exercise_id}")
async def get_exercise_image(request: Request, exercise_id: _EXERCISE_ID) -> Response:
    """Proxy permitted media only; never expose a credential or save the image."""
    try:
        image, content_type = await _catalog(request).get_image(exercise_id)
    except ExerciseNotFoundError as error:
        raise HTTPException(status_code=404, detail="Exercise image not found.") from error
    except ExerciseCatalogUnavailableError as error:
        return _unavailable(error)
    return Response(content=image, media_type=content_type, headers={"Cache-Control": "no-store"})


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
