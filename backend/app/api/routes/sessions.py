"""Performed and ad-hoc workout session APIs."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUserId, DatabaseSession
from app.api.exercise_sources import resolve_selection
from app.api.models import (
    ExerciseAdd,
    NotePatch,
    OrderWrite,
    PlanCreate,
    PlannedSetCreate,
    ProblemResponse,
    SessionCreate,
    SessionExerciseResponse,
    SessionPage,
    SessionResponse,
    SessionSetPatch,
    SessionSetResponse,
)
from app.api.workout_common import (
    bump_version,
    clean_row,
    compact_numbers,
    etag,
    lock_parent,
    optional_if_match,
    parse_version,
    problem,
    require_fields,
)

router = APIRouter(
    prefix="/api/workout-sessions",
    tags=["workout sessions"],
    responses={
        404: {"model": ProblemResponse},
        409: {"model": ProblemResponse},
        422: {"model": ProblemResponse},
        428: {"model": ProblemResponse},
        503: {"model": ProblemResponse},
    },
)
IfMatch = Annotated[str | None, Depends(optional_if_match)]


async def session_detail(db: DatabaseSession, session_id: UUID, owner_id: UUID) -> dict[str, Any]:
    session = (
        (
            await db.execute(
                text("""SELECT id,name,source_plan_id,status,started_at,finished_at,total_time_seconds,
        version,created_at,updated_at FROM workout_sessions WHERE id=:id AND owner_user_id=:owner"""),
                {"id": session_id, "owner": owner_id},
            )
        )
        .mappings()
        .first()
    )
    if session is None:
        raise problem(404, "not_found", "Workout session not found.")
    exercises = (
        (
            await db.execute(
                text("""SELECT id,exercise_order,source_kind,custom_exercise_id,external_provider,
        external_exercise_id,exercise_name,body_part,equipment,measurement_type,note FROM session_exercises
        WHERE session_id=:id AND owner_user_id=:owner ORDER BY exercise_order"""),
                {"id": session_id, "owner": owner_id},
            )
        )
        .mappings()
        .all()
    )
    result = clean_row(session)
    result["exercises"] = []
    exercise_ids = [row["id"] for row in exercises]
    all_sets = (
        (
            await db.execute(
                text("""SELECT id,session_exercise_id,set_number,measurement_type,target_reps,target_duration_seconds,
      target_weight_kg,rest_seconds,actual_reps,actual_duration_seconds,actual_weight_kg,status,completed_at
      FROM session_sets WHERE session_exercise_id=ANY(:ids) ORDER BY set_number"""),
                {"ids": exercise_ids},
            )
        )
        .mappings()
        .all()
        if exercise_ids
        else []
    )
    grouped: dict[UUID, list[dict[str, Any]]] = {}
    for row in all_sets:
        grouped.setdefault(row["session_exercise_id"], []).append(clean_row(row))
    for exercise in exercises:
        item = clean_row(exercise)
        item["sets"] = grouped.get(exercise["id"], [])
        for value in item["sets"]:
            value.pop("session_exercise_id", None)
        result["exercises"].append(item)
    return result


@router.get("", response_model=SessionPage)
async def list_sessions(
    user_id: CurrentUserId,
    db: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(in_progress|finished|abandoned)$")
    ] = None,
) -> dict[str, Any]:
    clause = "AND status=:status" if status_filter else ""
    params = {
        "owner": user_id,
        "status": status_filter,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    rows = (
        (
            await db.execute(
                text(f"""SELECT id,name,source_plan_id,status,started_at,finished_at,total_time_seconds,version
        FROM workout_sessions WHERE owner_user_id=:owner {clause} ORDER BY started_at DESC LIMIT :limit OFFSET :offset"""),
                params,
            )
        )
        .mappings()
        .all()
    )
    total = await db.scalar(
        text(f"SELECT count(*) FROM workout_sessions WHERE owner_user_id=:owner {clause}"), params
    )
    return {
        "items": [clean_row(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(
    body: SessionCreate, user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    if body.source_plan_id is not None and body.name is not None:
        raise problem(422, "validation_error", "A plan-based session cannot override its name.")
    plan = None
    if body.source_plan_id is not None:
        plan = (
            (
                await db.execute(
                    text(
                        "SELECT * FROM workout_plans WHERE id=:id AND owner_user_id=:owner FOR SHARE"
                    ),
                    {"id": body.source_plan_id, "owner": user_id},
                )
            )
            .mappings()
            .first()
        )
        if plan is None:
            raise problem(404, "not_found", "Workout plan not found.")
        if plan["archived_at"] is not None:
            raise problem(409, "archived_resource", "Archived plans cannot start sessions.")
    try:
        session_id = (
            await db.execute(
                text(
                    "INSERT INTO workout_sessions (owner_user_id,source_plan_id,name) VALUES (:owner,:plan,:name) RETURNING id"
                ),
                {
                    "owner": user_id,
                    "plan": body.source_plan_id,
                    "name": plan["name"] if plan else body.name,
                },
            )
        ).scalar_one()
    except IntegrityError as error:
        await db.rollback()
        raise problem(
            409, "active_session_exists", "An in-progress workout already exists."
        ) from error
    if plan:
        source_exercises = (
            (
                await db.execute(
                    text("SELECT * FROM plan_exercises WHERE plan_id=:id ORDER BY exercise_order"),
                    {"id": body.source_plan_id},
                )
            )
            .mappings()
            .all()
        )
        for exercise in source_exercises:
            new_item = (
                await db.execute(
                    text("""INSERT INTO session_exercises
                (session_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,external_exercise_record_id,exercise_name,body_part,equipment,measurement_type,note)
                VALUES (:session,:owner,:exercise_order,:source_kind,:custom_exercise_id,:external_provider,:external_exercise_id,:external_exercise_record_id,:exercise_name,:body_part,:equipment,:measurement_type,:note) RETURNING id"""),
                    {
                        **dict(exercise),
                        "session": session_id,
                        "owner": user_id,
                    },
                )
            ).scalar_one()
            await db.execute(
                text("""INSERT INTO session_sets
                (session_exercise_id,set_number,measurement_type,target_reps,target_weight_kg,target_duration_seconds,rest_seconds)
                SELECT :new,set_number,measurement_type,target_reps,target_weight_kg,target_duration_seconds,rest_seconds FROM plan_sets WHERE plan_exercise_id=:old ORDER BY set_number"""),
                {"new": new_item, "old": exercise["id"]},
            )
    detail = await session_detail(db, session_id, user_id)
    await db.commit()
    response.headers.update(etag(1))
    response.headers["Location"] = f"/api/workout-sessions/{session_id}"
    return detail


@router.get(
    "/current",
    response_model=SessionResponse,
    operation_id="getCurrentWorkout",
    summary="Get current workout",
)
async def current_session(
    user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    """Restore the user's single active workout and its current ETag."""
    session_id = await db.scalar(
        text("SELECT id FROM workout_sessions WHERE owner_user_id=:owner AND status='in_progress'"),
        {"owner": user_id},
    )
    if session_id is None:
        raise problem(404, "no_active_session", "No in-progress workout exists.")
    detail = await session_detail(db, session_id, user_id)
    response.headers.update(etag(detail["version"]))
    return detail


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID, user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    detail = await session_detail(db, session_id, user_id)
    response.headers.update(etag(detail["version"]))
    return detail


@router.delete(
    "/{session_id}",
    status_code=204,
    operation_id="cancelWorkout",
    summary="Permanently cancel workout",
)
async def cancel_session(
    session_id: UUID, if_match: IfMatch, user_id: CurrentUserId, db: DatabaseSession
) -> Response:
    """Hard-delete an active session and its cascade-owned children atomically."""
    await _mutable_session(db, session_id, user_id, if_match)
    await db.execute(text("DELETE FROM workout_sessions WHERE id=:id"), {"id": session_id})
    await db.commit()
    return Response(status_code=204)


async def _mutable_session(
    db: DatabaseSession, session_id: UUID, user_id: UUID, if_match: str | None
) -> None:
    parent = await lock_parent(db, "workout_sessions", session_id, user_id, parse_version(if_match))
    if parent["status"] != "in_progress":
        raise problem(409, "terminal_session", "Completed sessions are read-only.")


@router.patch("/{session_id}", response_model=SessionResponse)
async def rename_session(
    session_id: UUID,
    body: PlanCreate,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    await db.execute(
        text("UPDATE workout_sessions SET name=:name WHERE id=:id"),
        {"name": body.name, "id": session_id},
    )
    version = await bump_version(db, "workout_sessions", session_id)
    detail = await session_detail(db, session_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return detail


async def _session_item(db: DatabaseSession, session_id: UUID, item_id: UUID, owner: UUID) -> Any:
    row = (
        (
            await db.execute(
                text(
                    "SELECT * FROM session_exercises WHERE id=:item AND session_id=:session AND owner_user_id=:owner"
                ),
                {"item": item_id, "session": session_id, "owner": owner},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Session exercise not found.")
    return row


@router.post("/{session_id}/exercises", status_code=201, response_model=SessionExerciseResponse)
async def add_session_exercise(
    session_id: UUID,
    body: ExerciseAdd,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    count = await db.scalar(
        text("SELECT count(*) FROM session_exercises WHERE session_id=:id"), {"id": session_id}
    )
    if count >= 50:
        raise problem(409, "limit_reached", "A session may contain at most 50 exercises.")
    snapshot = await resolve_selection(body, user_id, db, request)
    row = (
        (
            await db.execute(
                text("""INSERT INTO session_exercises
        (session_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,external_exercise_record_id,exercise_name,body_part,equipment,measurement_type,note)
        VALUES (:session,:owner,:position,:source_kind,:custom_exercise_id,:external_provider,:external_exercise_id,:external_exercise_record_id,:exercise_name,:body_part,:equipment,:measurement_type,:note)
        RETURNING id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,exercise_name,body_part,equipment,measurement_type,note"""),
                {**snapshot, "session": session_id, "owner": user_id, "position": int(count) + 1},
            )
        )
        .mappings()
        .one()
    )
    version = await bump_version(db, "workout_sessions", session_id)
    await db.commit()
    result = clean_row(row)
    result["sets"] = []
    response.headers.update(etag(version))
    response.headers["Location"] = f"/api/workout-sessions/{session_id}/exercises/{row['id']}"
    return result


@router.patch("/{session_id}/exercises/{item_id}", response_model=SessionExerciseResponse)
async def patch_session_exercise(
    session_id: UUID,
    item_id: UUID,
    body: NotePatch,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    await _session_item(db, session_id, item_id, user_id)
    await db.execute(
        text("UPDATE session_exercises SET note=:note WHERE id=:id"),
        {"note": body.note, "id": item_id},
    )
    version = await bump_version(db, "workout_sessions", session_id)
    detail = await session_detail(db, session_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return next(item for item in detail["exercises"] if item["id"] == item_id)


@router.delete("/{session_id}/exercises/{item_id}", status_code=204)
async def delete_session_exercise(
    session_id: UUID,
    item_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> Response:
    await _mutable_session(db, session_id, user_id, if_match)
    await _session_item(db, session_id, item_id, user_id)
    await db.execute(
        text("DELETE FROM session_sets WHERE session_exercise_id=:id"), {"id": item_id}
    )
    await db.execute(text("DELETE FROM session_exercises WHERE id=:id"), {"id": item_id})
    await compact_numbers(db, "session_exercises", "session_id", session_id, "exercise_order")
    version = await bump_version(db, "workout_sessions", session_id)
    await db.commit()
    return Response(status_code=204, headers=etag(version))


@router.put("/{session_id}/exercises/order", response_model=SessionResponse)
async def reorder_session_exercises(
    session_id: UUID,
    body: OrderWrite,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    current = list(
        (
            await db.execute(
                text("SELECT id FROM session_exercises WHERE session_id=:id"), {"id": session_id}
            )
        ).scalars()
    )
    if len(body.exercise_ids) != len(set(body.exercise_ids)) or set(body.exercise_ids) != set(
        current
    ):
        raise problem(
            422, "invalid_order", "Exercise order must contain every current exercise exactly once."
        )
    await db.execute(
        text(
            "UPDATE session_exercises SET exercise_order=exercise_order+10000 WHERE session_id=:id"
        ),
        {"id": session_id},
    )
    for position, item_id in enumerate(body.exercise_ids, 1):
        await db.execute(
            text("UPDATE session_exercises SET exercise_order=:position WHERE id=:id"),
            {"position": position, "id": item_id},
        )
    version = await bump_version(db, "workout_sessions", session_id)
    detail = await session_detail(db, session_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return detail


@router.post(
    "/{session_id}/exercises/{item_id}/sets",
    status_code=201,
    response_model=SessionSetResponse,
)
async def add_session_set(
    session_id: UUID,
    item_id: UUID,
    body: PlannedSetCreate,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    parent = await _session_item(db, session_id, item_id, user_id)
    count = await db.scalar(
        text("SELECT count(*) FROM session_sets WHERE session_exercise_id=:id"), {"id": item_id}
    )
    if count >= 20:
        raise problem(409, "limit_reached", "An exercise may contain at most 20 sets.")
    if parent["measurement_type"] == "reps" and (
        body.target_reps is None or body.target_duration_seconds is not None
    ):
        raise problem(
            422, "invalid_measurement", "A repetitions exercise requires reps and rejects duration."
        )
    if parent["measurement_type"] == "duration" and (
        body.target_duration_seconds is None or body.target_reps is not None
    ):
        raise problem(
            422, "invalid_measurement", "A duration exercise requires duration and rejects reps."
        )
    row = (
        (
            await db.execute(
                text("""INSERT INTO session_sets (session_exercise_id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds)
        VALUES (:item,:number,:measurement,:reps,:duration,:weight,:rest) RETURNING id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds,actual_reps,actual_duration_seconds,actual_weight_kg,status,completed_at"""),
                {
                    "item": item_id,
                    "number": int(count) + 1,
                    "reps": body.target_reps,
                    "duration": body.target_duration_seconds,
                    "weight": body.target_weight_kg,
                    "rest": body.rest_seconds,
                    "measurement": parent["measurement_type"],
                },
            )
        )
        .mappings()
        .one()
    )
    version = await bump_version(db, "workout_sessions", session_id)
    await db.commit()
    response.headers.update(etag(version))
    response.headers["Location"] = (
        f"/api/workout-sessions/{session_id}/exercises/{item_id}/sets/{row['id']}"
    )
    return clean_row(row)


async def _session_set(db: DatabaseSession, item_id: UUID, set_id: UUID) -> Any:
    row = (
        (
            await db.execute(
                text("SELECT * FROM session_sets WHERE id=:id AND session_exercise_id=:item"),
                {"id": set_id, "item": item_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Session set not found.")
    return row


@router.patch("/{session_id}/exercises/{item_id}/sets/{set_id}", response_model=SessionSetResponse)
async def patch_session_set(
    session_id: UUID,
    item_id: UUID,
    set_id: UUID,
    body: SessionSetPatch,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    require_fields(body.model_fields_set)
    await _mutable_session(db, session_id, user_id, if_match)
    await _session_item(db, session_id, item_id, user_id)
    current = await _session_set(db, item_id, set_id)
    values = body.model_dump(exclude_unset=True)
    desired = values.get("status", current["status"])
    measurement = current["measurement_type"]
    target_reps = values.get("target_reps", current["target_reps"])
    target_duration = values.get("target_duration_seconds", current["target_duration_seconds"])
    if measurement == "reps" and (target_reps is None or target_duration is not None):
        raise problem(
            422, "invalid_measurement", "A repetitions exercise requires reps and rejects duration."
        )
    if measurement == "duration" and (target_duration is None or target_reps is not None):
        raise problem(
            422, "invalid_measurement", "A duration exercise requires duration and rejects reps."
        )
    actual_fields = {"actual_reps", "actual_duration_seconds", "actual_weight_kg"} & values.keys()
    if desired in {"planned", "skipped"} and actual_fields:
        raise problem(
            422, "actual_values_require_completed", "Actual values require completed status."
        )
    if desired in {"planned", "skipped"}:
        values.update(
            {
                "actual_reps": None,
                "actual_duration_seconds": None,
                "actual_weight_kg": None,
                "completed_at": None,
            }
        )
    elif desired == "completed":
        actual_reps = values.get("actual_reps", current["actual_reps"])
        actual_duration = values.get("actual_duration_seconds", current["actual_duration_seconds"])
        if measurement == "reps" and (actual_reps is None or actual_duration is not None):
            raise problem(
                422, "completion_requires_reps", "A completed repetitions set requires actual reps."
            )
        if measurement == "duration" and (actual_duration is None or actual_reps is not None):
            raise problem(
                422,
                "completion_requires_duration",
                "A completed duration set requires actual seconds.",
            )
        # First completion establishes history time; later result edits preserve it.
        values["completed_at"] = current["completed_at"] or datetime.now(UTC)
    assignments = [f"{key}=:{key}" for key in values]
    row = (
        (
            await db.execute(
                text(
                    f"UPDATE session_sets SET {', '.join(assignments)} WHERE id=:id RETURNING id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds,actual_reps,actual_duration_seconds,actual_weight_kg,status,completed_at"
                ),
                {**values, "id": set_id},
            )
        )
        .mappings()
        .one()
    )
    version = await bump_version(db, "workout_sessions", session_id)
    await db.commit()
    response.headers.update(etag(version))
    return clean_row(row)


@router.delete("/{session_id}/exercises/{item_id}/sets/{set_id}", status_code=204)
async def delete_session_set(
    session_id: UUID,
    item_id: UUID,
    set_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> Response:
    await _mutable_session(db, session_id, user_id, if_match)
    await _session_item(db, session_id, item_id, user_id)
    await _session_set(db, item_id, set_id)
    await db.execute(text("DELETE FROM session_sets WHERE id=:id"), {"id": set_id})
    await compact_numbers(db, "session_sets", "session_exercise_id", item_id, "set_number")
    version = await bump_version(db, "workout_sessions", session_id)
    await db.commit()
    return Response(status_code=204, headers=etag(version))


async def _transition(
    session_id: UUID,
    action: str,
    if_match: str | None,
    user_id: UUID,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_session(db, session_id, user_id, if_match)
    if action == "finished":
        counts = (
            await db.execute(
                text("""SELECT count(DISTINCT e.id),count(s.id),count(*) FILTER (WHERE s.status='planned')
            FROM session_exercises e LEFT JOIN session_sets s ON s.session_exercise_id=e.id WHERE e.session_id=:id"""),
                {"id": session_id},
            )
        ).one()
        if counts[0] < 1 or counts[1] < 1 or counts[2] > 0:
            raise problem(
                409,
                "incomplete_session",
                "Finish requires an exercise and set, with every set completed or skipped.",
            )
    await db.execute(
        text("""UPDATE workout_sessions SET status=:status,finished_at=now(),
        total_time_seconds=greatest(0,extract(epoch from (now()-started_at))::int) WHERE id=:id"""),
        {"status": action, "id": session_id},
    )
    version = await bump_version(db, "workout_sessions", session_id)
    detail = await session_detail(db, session_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return detail


@router.post("/{session_id}/finish", response_model=SessionResponse)
async def finish_session(
    session_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    return await _transition(session_id, "finished", if_match, user_id, db, response)


@router.post("/{session_id}/abandon", response_model=SessionResponse)
async def abandon_session(
    session_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    return await _transition(session_id, "abandoned", if_match, user_id, db, response)
