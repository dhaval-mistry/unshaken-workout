"""Owner-scoped reusable workout-plan APIs."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from sqlalchemy import text

from app.api.dependencies import CurrentUserId, DatabaseSession
from app.api.exercise_sources import resolve_selection
from app.api.models import (
    ExerciseAdd,
    NotePatch,
    OrderWrite,
    PlanCreate,
    PlanDuplicate,
    PlanExerciseResponse,
    PlannedSetCreate,
    PlannedSetPatch,
    PlannedSetResponse,
    PlanPage,
    PlanResponse,
    ProblemResponse,
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
    prefix="/api/workout-plans",
    tags=["workout plans"],
    responses={
        404: {"model": ProblemResponse},
        409: {"model": ProblemResponse},
        422: {"model": ProblemResponse},
        428: {"model": ProblemResponse},
        503: {"model": ProblemResponse},
    },
)
IfMatch = Annotated[str | None, Depends(optional_if_match)]


async def plan_detail(db: DatabaseSession, plan_id: UUID, owner_id: UUID) -> dict[str, Any]:
    plan = (
        (
            await db.execute(
                text(
                    """SELECT p.id,p.name,p.archived_at,p.version,p.created_at,p.updated_at,
                    (SELECT max(s.finished_at) FROM workout_sessions s WHERE s.source_plan_id=p.id AND s.owner_user_id=:owner AND s.status='finished') last_performed_at
                    FROM workout_plans p WHERE p.id=:id AND p.owner_user_id=:owner"""
                ),
                {"id": plan_id, "owner": owner_id},
            )
        )
        .mappings()
        .first()
    )
    if plan is None:
        raise problem(404, "not_found", "Workout plan not found.")
    exercises = (
        (
            await db.execute(
                text(
                    """SELECT id, exercise_order, source_kind, custom_exercise_id,
                external_provider, external_exercise_id, exercise_name,body_part,equipment,measurement_type,note FROM plan_exercises
                WHERE plan_id=:id AND owner_user_id=:owner ORDER BY exercise_order"""
                ),
                {"id": plan_id, "owner": owner_id},
            )
        )
        .mappings()
        .all()
    )
    result = clean_row(plan)
    result["exercises"] = []
    exercise_ids = [row["id"] for row in exercises]
    all_sets = (
        (
            await db.execute(
                text("""SELECT id,plan_exercise_id,set_number,measurement_type,target_reps,
      target_duration_seconds,target_weight_kg,rest_seconds FROM plan_sets WHERE plan_exercise_id=ANY(:ids) ORDER BY set_number"""),
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
        grouped.setdefault(row["plan_exercise_id"], []).append(clean_row(row) | {})
    for exercise in exercises:
        item = clean_row(exercise)
        item["sets"] = grouped.get(exercise["id"], [])
        for value in item["sets"]:
            value.pop("plan_exercise_id", None)
        result["exercises"].append(item)
    return result


@router.get("", response_model=PlanPage)
async def list_plans(
    user_id: CurrentUserId,
    db: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    include_archived: bool = False,
    query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort: Annotated[
        str, Query(pattern="^(updated_desc|name_asc|last_performed_desc)$")
    ] = "updated_desc",
) -> dict[str, Any]:
    archive = "" if include_archived else "AND p.archived_at IS NULL"
    name_filter = "" if query is None else "AND p.name ILIKE '%'||:query||'%'"
    order = {
        "updated_desc": "p.updated_at DESC,p.id",
        "name_asc": "lower(p.name),p.id",
        "last_performed_desc": "last_performed_at DESC NULLS LAST,p.id",
    }[sort]
    params = {
        "owner": user_id,
        "query": query,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    rows = (
        (
            await db.execute(
                text(
                    f"""SELECT p.id,p.name,p.archived_at,p.version,p.created_at,p.updated_at,
                (SELECT count(*)::int FROM plan_exercises e WHERE e.plan_id=p.id) exercise_count,
                (SELECT max(s.finished_at) FROM workout_sessions s WHERE s.source_plan_id=p.id AND s.status='finished') last_performed_at,
                coalesce((SELECT json_agg(json_build_object('name',q.exercise_name,'set_count',q.set_count,'measurement_type',q.measurement_type) ORDER BY q.exercise_order)
                  FROM (SELECT e.exercise_name,e.measurement_type,e.exercise_order,count(ps.id)::int set_count FROM plan_exercises e LEFT JOIN plan_sets ps ON ps.plan_exercise_id=e.id WHERE e.plan_id=p.id GROUP BY e.id ORDER BY e.exercise_order LIMIT 3) q),'[]'::json) exercise_preview
                FROM workout_plans p WHERE p.owner_user_id=:owner {archive}
                {name_filter} ORDER BY {order} LIMIT :limit OFFSET :offset"""
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    total = await db.scalar(
        text(
            f"SELECT count(*) FROM workout_plans p WHERE p.owner_user_id=:owner {archive} {name_filter}"
        ),
        params,
    )
    return {
        "items": [clean_row(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PlanResponse)
async def create_plan(
    body: PlanCreate, user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                "INSERT INTO workout_plans (owner_user_id, name) VALUES (:owner, :name) RETURNING id"
            ),
            {"owner": user_id, "name": body.name},
        )
    ).one()
    detail = await plan_detail(db, row[0], user_id)
    await db.commit()
    response.headers.update(etag(detail["version"]))
    response.headers["Location"] = f"/api/workout-plans/{row[0]}"
    return detail


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID, user_id: CurrentUserId, db: DatabaseSession, response: Response
) -> dict[str, Any]:
    detail = await plan_detail(db, plan_id, user_id)
    response.headers.update(etag(detail["version"]))
    return detail


@router.patch("/{plan_id}", response_model=PlanResponse)
async def rename_plan(
    plan_id: UUID,
    body: PlanCreate,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    version = parse_version(if_match)
    parent = await lock_parent(db, "workout_plans", plan_id, user_id, version)
    if parent["archived_at"] is not None:
        raise problem(409, "archived_resource", "Archived plans are read-only.")
    await db.execute(
        text("UPDATE workout_plans SET name=:name WHERE id=:id"), {"name": body.name, "id": plan_id}
    )
    new_version = await bump_version(db, "workout_plans", plan_id)
    detail = await plan_detail(db, plan_id, user_id)
    await db.commit()
    response.headers.update(etag(new_version))
    return detail


@router.post("/{plan_id}/duplicate", status_code=201, response_model=PlanResponse)
async def duplicate_plan(
    plan_id: UUID,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
    body: Annotated[PlanDuplicate | None, Body()] = None,
) -> dict[str, Any]:
    source = (
        (
            await db.execute(
                text("SELECT * FROM workout_plans WHERE id=:id AND owner_user_id=:owner FOR SHARE"),
                {"id": plan_id, "owner": user_id},
            )
        )
        .mappings()
        .first()
    )
    if source is None:
        raise problem(404, "not_found", "Workout plan not found.")
    if source["archived_at"] is not None:
        raise problem(409, "archived_resource", "Archived plans cannot be duplicated.")
    new_id = (
        await db.execute(
            text(
                "INSERT INTO workout_plans (owner_user_id, name) VALUES (:owner, :name) RETURNING id"
            ),
            {
                "owner": user_id,
                "name": body.name if body and body.name else f"{source['name']} Copy",
            },
        )
    ).scalar_one()
    exercises = (
        (
            await db.execute(
                text("SELECT * FROM plan_exercises WHERE plan_id=:id ORDER BY exercise_order"),
                {"id": plan_id},
            )
        )
        .mappings()
        .all()
    )
    for exercise in exercises:
        new_exercise = (
            await db.execute(
                text("""INSERT INTO plan_exercises
            (plan_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,external_exercise_record_id,exercise_name,body_part,equipment,measurement_type,note)
            VALUES (:plan,:owner,:exercise_order,:source_kind,:custom_exercise_id,:external_provider,:external_exercise_id,:external_exercise_record_id,:exercise_name,:body_part,:equipment,:measurement_type,:note) RETURNING id"""),
                {**dict(exercise), "plan": new_id, "owner": user_id},
            )
        ).scalar_one()
        await db.execute(
            text("""INSERT INTO plan_sets (plan_exercise_id,set_number,measurement_type,target_reps,target_weight_kg,target_duration_seconds,rest_seconds)
            SELECT :new,set_number,measurement_type,target_reps,target_weight_kg,target_duration_seconds,rest_seconds
            FROM plan_sets WHERE plan_exercise_id=:old ORDER BY set_number"""),
            {"new": new_exercise, "old": exercise["id"]},
        )
    detail = await plan_detail(db, new_id, user_id)
    await db.commit()
    response.headers.update(etag(1))
    response.headers["Location"] = f"/api/workout-plans/{new_id}"
    return detail


@router.post("/{plan_id}/archive", response_model=PlanResponse)
async def archive_plan(
    plan_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    parent = await lock_parent(db, "workout_plans", plan_id, user_id, parse_version(if_match))
    if parent["archived_at"] is None:
        await db.execute(
            text("UPDATE workout_plans SET archived_at=now() WHERE id=:id"), {"id": plan_id}
        )
        new_version = await bump_version(db, "workout_plans", plan_id)
    else:
        new_version = int(parent["version"])
    detail = await plan_detail(db, plan_id, user_id)
    await db.commit()
    response.headers.update(etag(new_version))
    return detail


async def _mutable_plan(
    db: DatabaseSession, plan_id: UUID, user_id: UUID, if_match: str | None
) -> None:
    parent = await lock_parent(db, "workout_plans", plan_id, user_id, parse_version(if_match))
    if parent["archived_at"] is not None:
        raise problem(409, "archived_resource", "Archived plans are read-only.")


@router.post("/{plan_id}/exercises", status_code=201, response_model=PlanExerciseResponse)
async def add_plan_exercise(
    plan_id: UUID,
    body: ExerciseAdd,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    await _mutable_plan(db, plan_id, user_id, if_match)
    count = await db.scalar(
        text("SELECT count(*) FROM plan_exercises WHERE plan_id=:id"), {"id": plan_id}
    )
    if count >= 50:
        raise problem(409, "limit_reached", "A plan may contain at most 50 exercises.")
    snapshot = await resolve_selection(body, user_id, db, request)
    order = int(count) + 1
    item = (
        (
            await db.execute(
                text("""INSERT INTO plan_exercises
        (plan_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,external_exercise_record_id,exercise_name,body_part,equipment,measurement_type,note)
        VALUES (:plan,:owner,:position,:source_kind,:custom_exercise_id,:external_provider,:external_exercise_id,:external_exercise_record_id,:exercise_name,:body_part,:equipment,:measurement_type,:note)
        RETURNING id,exercise_order,source_kind,custom_exercise_id,external_provider,external_exercise_id,exercise_name,body_part,equipment,measurement_type,note"""),
                {**snapshot, "plan": plan_id, "owner": user_id, "position": order},
            )
        )
        .mappings()
        .one()
    )
    new_version = await bump_version(db, "workout_plans", plan_id)
    await db.commit()
    result = clean_row(item)
    result["sets"] = []
    response.headers.update(etag(new_version))
    response.headers["Location"] = f"/api/workout-plans/{plan_id}/exercises/{item['id']}"
    return result


async def _plan_item(db: DatabaseSession, plan_id: UUID, item_id: UUID, owner: UUID) -> Any:
    row = (
        (
            await db.execute(
                text(
                    "SELECT * FROM plan_exercises WHERE id=:item AND plan_id=:plan AND owner_user_id=:owner"
                ),
                {"item": item_id, "plan": plan_id, "owner": owner},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Plan exercise not found.")
    return row


@router.patch("/{plan_id}/exercises/{item_id}", response_model=PlanExerciseResponse)
async def patch_plan_exercise(
    plan_id: UUID,
    item_id: UUID,
    body: NotePatch,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_plan(db, plan_id, user_id, if_match)
    await _plan_item(db, plan_id, item_id, user_id)
    await db.execute(
        text("UPDATE plan_exercises SET note=:note WHERE id=:id"),
        {"note": body.note, "id": item_id},
    )
    version = await bump_version(db, "workout_plans", plan_id)
    detail = await plan_detail(db, plan_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return next(item for item in detail["exercises"] if item["id"] == item_id)


@router.delete("/{plan_id}/exercises/{item_id}", status_code=204)
async def delete_plan_exercise(
    plan_id: UUID,
    item_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> Response:
    await _mutable_plan(db, plan_id, user_id, if_match)
    await _plan_item(db, plan_id, item_id, user_id)
    await db.execute(text("DELETE FROM plan_sets WHERE plan_exercise_id=:id"), {"id": item_id})
    await db.execute(text("DELETE FROM plan_exercises WHERE id=:id"), {"id": item_id})
    await compact_numbers(db, "plan_exercises", "plan_id", plan_id, "exercise_order")
    version = await bump_version(db, "workout_plans", plan_id)
    await db.commit()
    return Response(status_code=204, headers=etag(version))


@router.put("/{plan_id}/exercises/order", response_model=PlanResponse)
async def reorder_plan_exercises(
    plan_id: UUID,
    body: OrderWrite,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_plan(db, plan_id, user_id, if_match)
    current = list(
        (
            await db.execute(
                text("SELECT id FROM plan_exercises WHERE plan_id=:id"), {"id": plan_id}
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
        text("UPDATE plan_exercises SET exercise_order=exercise_order+10000 WHERE plan_id=:id"),
        {"id": plan_id},
    )
    for position, item_id in enumerate(body.exercise_ids, 1):
        await db.execute(
            text("UPDATE plan_exercises SET exercise_order=:position WHERE id=:id"),
            {"position": position, "id": item_id},
        )
    version = await bump_version(db, "workout_plans", plan_id)
    detail = await plan_detail(db, plan_id, user_id)
    await db.commit()
    response.headers.update(etag(version))
    return detail


@router.post(
    "/{plan_id}/exercises/{item_id}/sets",
    status_code=201,
    response_model=PlannedSetResponse,
)
async def add_plan_set(
    plan_id: UUID,
    item_id: UUID,
    body: PlannedSetCreate,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    await _mutable_plan(db, plan_id, user_id, if_match)
    parent = await _plan_item(db, plan_id, item_id, user_id)
    count = await db.scalar(
        text("SELECT count(*) FROM plan_sets WHERE plan_exercise_id=:id"), {"id": item_id}
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
                text(
                    """INSERT INTO plan_sets (plan_exercise_id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds)
                    VALUES (:item,:number,:measurement,:reps,:duration,:weight,:rest)
                    RETURNING id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds"""
                ),
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
    version = await bump_version(db, "workout_plans", plan_id)
    await db.commit()
    response.headers.update(etag(version))
    response.headers["Location"] = (
        f"/api/workout-plans/{plan_id}/exercises/{item_id}/sets/{row['id']}"
    )
    return clean_row(row)


async def _plan_set(db: DatabaseSession, item_id: UUID, set_id: UUID) -> Any:
    row = (
        (
            await db.execute(
                text("SELECT * FROM plan_sets WHERE id=:id AND plan_exercise_id=:item"),
                {"id": set_id, "item": item_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Planned set not found.")
    return row


@router.patch("/{plan_id}/exercises/{item_id}/sets/{set_id}", response_model=PlannedSetResponse)
async def patch_plan_set(
    plan_id: UUID,
    item_id: UUID,
    set_id: UUID,
    body: PlannedSetPatch,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> dict[str, Any]:
    require_fields(body.model_fields_set)
    await _mutable_plan(db, plan_id, user_id, if_match)
    parent = await _plan_item(db, plan_id, item_id, user_id)
    current = await _plan_set(db, item_id, set_id)
    values = body.model_dump(exclude_unset=True)
    reps = values.get("target_reps", current["target_reps"])
    duration = values.get("target_duration_seconds", current["target_duration_seconds"])
    if parent["measurement_type"] == "reps" and (reps is None or duration is not None):
        raise problem(
            422, "invalid_measurement", "A repetitions exercise requires reps and rejects duration."
        )
    if parent["measurement_type"] == "duration" and (duration is None or reps is not None):
        raise problem(
            422, "invalid_measurement", "A duration exercise requires duration and rejects reps."
        )
    assignments = [f"{key}=:{key}" for key in values]
    row = (
        (
            await db.execute(
                text(
                    f"UPDATE plan_sets SET {', '.join(assignments)} WHERE id=:id RETURNING id,set_number,measurement_type,target_reps,target_duration_seconds,target_weight_kg,rest_seconds"
                ),
                {**values, "id": set_id},
            )
        )
        .mappings()
        .one()
    )
    version = await bump_version(db, "workout_plans", plan_id)
    await db.commit()
    response.headers.update(etag(version))
    return clean_row(row)


@router.delete("/{plan_id}/exercises/{item_id}/sets/{set_id}", status_code=204)
async def delete_plan_set(
    plan_id: UUID,
    item_id: UUID,
    set_id: UUID,
    if_match: IfMatch,
    user_id: CurrentUserId,
    db: DatabaseSession,
    response: Response,
) -> Response:
    await _mutable_plan(db, plan_id, user_id, if_match)
    await _plan_item(db, plan_id, item_id, user_id)
    await _plan_set(db, item_id, set_id)
    await db.execute(text("DELETE FROM plan_sets WHERE id=:id"), {"id": set_id})
    await compact_numbers(db, "plan_sets", "plan_exercise_id", item_id, "set_number")
    version = await bump_version(db, "workout_plans", plan_id)
    await db.commit()
    return Response(status_code=204, headers=etag(version))
