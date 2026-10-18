"""Profile and private custom-exercise routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import text

from app.api.dependencies import CurrentUserId, DatabaseSession
from app.api.models import (
    BodyPart,
    CustomExercisePage,
    CustomExercisePatch,
    CustomExerciseResponse,
    CustomExerciseWrite,
    Equipment,
    MeasurementType,
    ProblemResponse,
    ProfilePatch,
    ProfileResponse,
)
from app.api.workout_common import clean_row, problem, require_fields

router = APIRouter(
    prefix="/api",
    responses={
        404: {"model": ProblemResponse},
        409: {"model": ProblemResponse},
        422: {"model": ProblemResponse},
        503: {"model": ProblemResponse},
    },
)


@router.get("/me", response_model=ProfileResponse, tags=["Profile"])
async def get_me(user_id: CurrentUserId, db: DatabaseSession) -> dict[str, Any]:
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, display_name, email, preferred_weight_unit, created_at, updated_at FROM users WHERE id=:id"
                ),
                {"id": user_id},
            )
        )
        .mappings()
        .one()
    )
    return clean_row(row)


@router.patch("/me", response_model=ProfileResponse, tags=["Profile"])
async def patch_me(
    body: ProfilePatch, user_id: CurrentUserId, db: DatabaseSession
) -> dict[str, Any]:
    require_fields(body.model_fields_set)
    values = body.model_dump(exclude_unset=True)
    assignments = [f"{name}=:{name}" for name in values]
    row = (
        (
            await db.execute(
                text(
                    f"""UPDATE users SET {', '.join(assignments)}, updated_at=now()
                    WHERE id=:id RETURNING id, display_name, email, preferred_weight_unit,
                    created_at, updated_at"""
                ),
                {**values, "id": user_id},
            )
        )
        .mappings()
        .one()
    )
    await db.commit()
    return clean_row(row)


@router.get("/custom-exercises", response_model=CustomExercisePage, tags=["Custom exercises"])
async def list_custom_exercises(
    user_id: CurrentUserId,
    db: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    include_archived: bool = False,
    query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    equipment: Equipment | None = None,
    body_part: BodyPart | None = None,
    measurement_type: MeasurementType | None = None,
    sort: Annotated[str, Query(pattern="^(name_asc|name_desc|created_desc)$")] = "name_asc",
) -> dict[str, Any]:
    archive = "" if include_archived else "AND archived_at IS NULL"
    conditions: list[str] = []
    if query is not None:
        conditions.append("name ILIKE '%' || :query || '%'")
    if equipment is not None:
        conditions.append("equipment=:equipment")
    if body_part is not None:
        conditions.append("body_part=:body_part")
    if measurement_type is not None:
        conditions.append("measurement_type=:measurement")
    filters = "" if not conditions else " AND " + " AND ".join(conditions)
    order = {
        "name_asc": "lower(name), id",
        "name_desc": "lower(name) DESC, id",
        "created_desc": "created_at DESC, id",
    }[sort]
    params = {
        "owner": user_id,
        "query": query,
        "equipment": equipment,
        "body_part": body_part,
        "measurement": measurement_type,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    rows = (
        (
            await db.execute(
                text(
                    f"""SELECT id, name, training_type, equipment, body_part, measurement_type, instructions,
                notes, archived_at, created_at, updated_at FROM custom_exercises
                WHERE owner_user_id=:owner {archive} {filters} ORDER BY {order}
                LIMIT :limit OFFSET :offset"""
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    total = await db.scalar(
        text(
            f"SELECT count(*) FROM custom_exercises WHERE owner_user_id=:owner {archive} {filters}"
        ),
        params,
    )
    return {
        "items": [clean_row(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post(
    "/custom-exercises",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomExerciseResponse,
    tags=["Custom exercises"],
)
async def create_custom_exercise(
    body: CustomExerciseWrite, user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    values = body.model_dump()
    row = (
        (
            await db.execute(
                text(
                    """INSERT INTO custom_exercises
                    (owner_user_id, name, training_type, equipment, body_part, measurement_type, instructions, notes)
                    VALUES (:owner, :name, :training_type, :equipment, :body_part, :measurement_type, :instructions, :notes)
                    RETURNING id, name, training_type, equipment, body_part, measurement_type, instructions,
                    notes, archived_at, created_at, updated_at"""
                ),
                {**values, "owner": user_id},
            )
        )
        .mappings()
        .one()
    )
    await db.commit()
    response.headers["Location"] = f"/api/custom-exercises/{row['id']}"
    return clean_row(row)


async def _custom(db: DatabaseSession, user_id: UUID, exercise_id: UUID) -> Any:
    row = (
        (
            await db.execute(
                text(
                    """SELECT id, name, training_type, equipment, body_part, measurement_type, instructions,
                notes, archived_at, created_at, updated_at FROM custom_exercises
                WHERE id=:id AND owner_user_id=:owner"""
                ),
                {"id": exercise_id, "owner": user_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Custom exercise not found.")
    return row


@router.get(
    "/custom-exercises/{exercise_id}",
    response_model=CustomExerciseResponse,
    tags=["Custom exercises"],
)
async def get_custom_exercise(
    exercise_id: UUID, user_id: CurrentUserId, db: DatabaseSession
) -> dict[str, Any]:
    return clean_row(await _custom(db, user_id, exercise_id))


@router.patch(
    "/custom-exercises/{exercise_id}",
    response_model=CustomExerciseResponse,
    tags=["Custom exercises"],
)
async def patch_custom_exercise(
    exercise_id: UUID, body: CustomExercisePatch, user_id: CurrentUserId, db: DatabaseSession
) -> dict[str, Any]:
    require_fields(body.model_fields_set)
    current = await _custom(db, user_id, exercise_id)
    if current["archived_at"] is not None:
        raise problem(409, "archived_resource", "Archived exercises are read-only.")
    values = body.model_dump(exclude_unset=True)
    if "measurement_type" in values and values["measurement_type"] != current["measurement_type"]:
        referenced = await db.scalar(
            text("""SELECT EXISTS(SELECT 1 FROM plan_exercises WHERE custom_exercise_id=:id)
          OR EXISTS(SELECT 1 FROM session_exercises e JOIN workout_sessions s ON s.id=e.session_id
                    WHERE e.custom_exercise_id=:id AND s.status='in_progress')"""),
            {"id": exercise_id},
        )
        if referenced:
            raise problem(
                409,
                "exercise_in_use",
                "Measurement type cannot change while the exercise is in use.",
            )
    assignments = [f"{name}=:{name}" for name in values]
    row = (
        (
            await db.execute(
                text(
                    f"""UPDATE custom_exercises SET {', '.join(assignments)}, updated_at=now()
                    WHERE id=:id AND owner_user_id=:owner RETURNING id, name, training_type,
                    equipment, body_part, measurement_type, instructions, notes, archived_at, created_at, updated_at"""
                ),
                {**values, "id": exercise_id, "owner": user_id},
            )
        )
        .mappings()
        .one()
    )
    await db.commit()
    return clean_row(row)


@router.post(
    "/custom-exercises/{exercise_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Custom exercises"],
)
async def archive_custom_exercise(
    exercise_id: UUID, user_id: CurrentUserId, db: DatabaseSession
) -> Response:
    await _custom(db, user_id, exercise_id)
    await db.execute(
        text(
            "UPDATE custom_exercises SET archived_at=coalesce(archived_at, now()), updated_at=now() WHERE id=:id AND owner_user_id=:owner"
        ),
        {"id": exercise_id, "owner": user_id},
    )
    await db.commit()
    return Response(status_code=204)
