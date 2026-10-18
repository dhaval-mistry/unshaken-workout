# ruff: noqa: E501
"""Stable exercise options, unified catalog, and previous-performance APIs."""

import base64
import hashlib
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from app.api.dependencies import CurrentUserId, DatabaseSession
from app.api.models import (
    BodyPart,
    CatalogPage,
    Equipment,
    ExerciseOptionsResponse,
    LatestPerformanceResponse,
    ProblemResponse,
)
from app.api.workout_common import clean_row, problem
from app.domain.exercise_options import (
    BODY_PARTS,
    EQUIPMENT,
    MEASUREMENT_TYPES,
    map_body_part,
    map_equipment,
)
from app.infrastructure.exercise_db.client import ExerciseCatalogUnavailableError

router = APIRouter(
    prefix="/api", responses={422: {"model": ProblemResponse}, 503: {"model": ProblemResponse}}
)


@router.get(
    "/exercise-options",
    response_model=ExerciseOptionsResponse,
    tags=["exercise options"],
    operation_id="listExerciseOptions",
    summary="List stable exercise options",
)
async def exercise_options() -> dict[str, Any]:
    """Return controlled values without contacting PostgreSQL or ExerciseDB."""
    return {
        "equipment": [{"key": k, "label": v} for k, v in EQUIPMENT.items()],
        "body_parts": [{"key": k, "label": v} for k, v in BODY_PARTS.items()],
        "measurement_types": [{"key": k, "label": v} for k, v in MEASUREMENT_TYPES.items()],
    }


def _cursor(signature: str, custom_offset: int, external_offset: int) -> str:
    raw = json.dumps(
        {"v": 1, "s": signature, "c": custom_offset, "e": external_offset}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str, signature: str) -> tuple[int, int]:
    try:
        body = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if body.get("v") != 1 or body.get("s") != signature:
            raise ValueError
        return int(body["c"]), int(body["e"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise problem(
            422, "invalid_cursor", "The catalog cursor is invalid for these filters."
        ) from error


@router.get(
    "/exercise-catalog",
    response_model=CatalogPage,
    tags=["exercise catalog"],
    operation_id="browseExerciseCatalog",
    summary="Browse selectable exercises",
)
async def exercise_catalog(
    request: Request,
    user_id: CurrentUserId,
    db: DatabaseSession,
    query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    body_part: BodyPart | None = None,
    equipment: Equipment | None = None,
    measurement_type: Literal["reps", "duration"] | None = None,
    source: Literal["all", "custom", "exercisedb"] = "all",
    cursor: str | None = None,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    """Merge bounded private and provider pages; browsing never persists vendor content."""
    filters = {
        "query": query,
        "body_part": body_part,
        "equipment": equipment,
        "measurement_type": measurement_type,
        "source": source,
    }
    signature = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:16]
    custom_offset, external_offset = _decode_cursor(cursor, signature) if cursor else (0, 0)
    custom: list[dict[str, Any]] = []
    if source != "exercisedb":
        custom_conditions = ["owner_user_id=:owner", "archived_at IS NULL"]
        if query is not None:
            custom_conditions.append("name ILIKE '%'||:query||'%'")
        if body_part is not None:
            custom_conditions.append("body_part=:body")
        if equipment is not None:
            custom_conditions.append("equipment=:equipment")
        if measurement_type is not None:
            custom_conditions.append("measurement_type=:measurement")
        rows = (
            (
                await db.execute(
                    text(f"""SELECT id,name,body_part,equipment,measurement_type FROM custom_exercises
          WHERE {' AND '.join(custom_conditions)}
          ORDER BY lower(name),id LIMIT :limit OFFSET :offset"""),
                    {
                        "owner": user_id,
                        "query": query,
                        "body": body_part,
                        "equipment": equipment,
                        "measurement": measurement_type,
                        "limit": page_size + 1,
                        "offset": custom_offset,
                    },
                )
            )
            .mappings()
            .all()
        )
        custom = [
            {
                "source_kind": "custom",
                "custom_exercise_id": r["id"],
                "external_provider": None,
                "external_exercise_id": None,
                "name": r["name"],
                "body_part": r["body_part"],
                "equipment": r["equipment"],
                "measurement_type": r["measurement_type"],
                "measurement_type_required_on_selection": False,
                "is_archived": False,
                "provider_attribution": None,
            }
            for r in rows
        ]

    external: list[dict[str, Any]] = []
    provider_status = "not_requested"
    if source != "custom" and measurement_type is None:
        stored_conditions: list[str] = []
        if query is not None:
            stored_conditions.append("name ILIKE '%'||:query||'%'")
        if body_part is not None:
            stored_conditions.append("body_part=:body")
        if equipment is not None:
            stored_conditions.append("equipment=:equipment")
        stored_where = "TRUE" if not stored_conditions else " AND ".join(stored_conditions)
        stored = (
            (
                await db.execute(
                    text(f"""SELECT external_exercise_id,name,body_part,equipment,attribution FROM external_exercises
          WHERE {stored_where} ORDER BY lower(name),external_exercise_id LIMIT :limit OFFSET :offset"""),
                    {
                        "query": query,
                        "body": body_part,
                        "equipment": equipment,
                        "limit": page_size + 1,
                        "offset": external_offset,
                    },
                )
            )
            .mappings()
            .all()
        )
        stored_items = [
            {
                "source_kind": "external",
                "custom_exercise_id": None,
                "external_provider": "exercisedb",
                "external_exercise_id": r["external_exercise_id"],
                "name": r["name"],
                "body_part": r["body_part"],
                "equipment": r["equipment"],
                "measurement_type": None,
                "measurement_type_required_on_selection": True,
                "is_archived": False,
                "provider_attribution": r["attribution"],
            }
            for r in stored
        ]
        try:
            result = await request.app.state.exercise_catalog.search(
                query=query,
                body_part=None,
                equipment=None,
                target=None,
                exercise_type=None,
                limit=min(50, page_size + 1),
                offset=external_offset,
            )
            live = []
            for item in result.items:
                mapped_body = map_body_part(item.body_parts[0] if item.body_parts else None)
                mapped_equipment = map_equipment(item.equipment[0] if item.equipment else None)
                if (
                    body_part
                    and mapped_body != body_part
                    or equipment
                    and mapped_equipment != equipment
                ):
                    continue
                live.append(
                    {
                        "source_kind": "external",
                        "custom_exercise_id": None,
                        "external_provider": "exercisedb",
                        "external_exercise_id": item.id,
                        "name": item.name,
                        "body_part": mapped_body,
                        "equipment": mapped_equipment,
                        "measurement_type": None,
                        "measurement_type_required_on_selection": True,
                        "is_archived": False,
                        "provider_attribution": "ExerciseDB",
                    }
                )
            by_id = {item["external_exercise_id"]: item for item in stored_items}
            by_id.update({item["external_exercise_id"]: item for item in live})
            external = list(by_id.values())
            provider_status = "available"
        except ExerciseCatalogUnavailableError as error:
            external = stored_items
            provider_status = "degraded"
            if source == "exercisedb" and not external:
                raise problem(
                    503, "catalog_unavailable", "The exercise catalog is temporarily unavailable."
                ) from error

    combined = sorted(
        custom + external,
        key=lambda x: (
            x["name"].casefold(),
            x["source_kind"],
            str(x.get("custom_exercise_id") or x.get("external_exercise_id")),
        ),
    )
    page = combined[:page_size]
    custom_used = sum(i["source_kind"] == "custom" for i in page)
    external_used = sum(i["source_kind"] == "external" for i in page)
    more = len(combined) > page_size or len(custom) > page_size or len(external) > page_size
    return {
        "items": page,
        "page_size": page_size,
        "next_cursor": _cursor(
            signature, custom_offset + custom_used, external_offset + external_used
        )
        if more
        else None,
        "provider_status": provider_status,
    }


@router.get(
    "/exercise-performance/latest",
    response_model=LatestPerformanceResponse,
    tags=["exercise performance"],
    operation_id="getLatestExercisePerformance",
    summary="Get latest performance",
)
async def latest_performance(
    user_id: CurrentUserId,
    db: DatabaseSession,
    source_kind: Literal["custom", "external"],
    custom_exercise_id: UUID | None = None,
    external_provider: str | None = None,
    external_exercise_id: str | None = None,
) -> dict[str, Any]:
    """Select the latest finished snapshot, so the provider is never needed for history."""
    params: dict[str, Any]
    if source_kind == "custom":
        if custom_exercise_id is None or external_provider or external_exercise_id:
            raise problem(422, "validation_error", "Provide exactly one complete exercise source.")
        exists = await db.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM custom_exercises WHERE id=:id AND owner_user_id=:owner)"
            ),
            {"id": custom_exercise_id, "owner": user_id},
        )
        if not exists:
            raise problem(404, "not_found", "Custom exercise not found.")
        source_sql, params = "e.custom_exercise_id=:source_id", {"source_id": custom_exercise_id}
    else:
        if external_provider != "exercisedb" or not external_exercise_id or custom_exercise_id:
            raise problem(422, "validation_error", "Provide exactly one complete exercise source.")
        source_sql, params = (
            "e.external_provider=:provider AND e.external_exercise_id=:source_id",
            {"provider": external_provider, "source_id": external_exercise_id},
        )
    row = (
        (
            await db.execute(
                text(f"""SELECT s.id session_id,s.name session_name,s.finished_at,e.id session_exercise_id,e.exercise_name,e.measurement_type
      FROM workout_sessions s JOIN session_exercises e ON e.session_id=s.id
      WHERE s.owner_user_id=:owner AND s.status='finished' AND {source_sql}
      ORDER BY s.finished_at DESC,s.id DESC,e.exercise_order DESC LIMIT 1"""),
                {"owner": user_id, **params},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return {"item": None}
    sets = (
        (
            await db.execute(
                text(
                    "SELECT set_number,actual_reps,actual_duration_seconds,actual_weight_kg,status FROM session_sets WHERE session_exercise_id=:id ORDER BY set_number"
                ),
                {"id": row["session_exercise_id"]},
            )
        )
        .mappings()
        .all()
    )
    item = clean_row(row)
    item["sets"] = [clean_row(value) for value in sets]
    return {"item": item}
