# ruff: noqa: E501
"""Resolve custom or ExerciseDB selections into trusted database snapshots."""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import DatabaseSession
from app.api.models import CustomExerciseAdd, ExternalExerciseAdd
from app.api.workout_common import problem
from app.domain.exercise_options import map_body_part, map_equipment
from app.infrastructure.exercise_db.client import (
    ExerciseCatalogUnavailableError,
    ExerciseNotFoundError,
)


async def resolve_selection(
    body: CustomExerciseAdd | ExternalExerciseAdd,
    owner: UUID,
    db: DatabaseSession,
    request: Request,
) -> dict[str, Any]:
    """Return trusted snapshot fields; first external selection and occurrence share one transaction."""
    if body.source_kind == "custom":
        row = (
            (
                await db.execute(
                    text("""SELECT id,name,body_part,equipment,measurement_type FROM custom_exercises
          WHERE id=:id AND owner_user_id=:owner AND archived_at IS NULL"""),
                    {"id": body.custom_exercise_id, "owner": owner},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise problem(404, "not_found", "Custom exercise not found.")
        return {
            "source_kind": "custom",
            "custom_exercise_id": row["id"],
            "external_provider": None,
            "external_exercise_id": None,
            "external_exercise_record_id": None,
            "exercise_name": row["name"],
            "body_part": row["body_part"],
            "equipment": row["equipment"],
            "measurement_type": row["measurement_type"],
            "note": body.note,
        }

    stored = (
        (
            await db.execute(
                text(
                    "SELECT * FROM external_exercises WHERE provider='exercisedb' AND external_exercise_id=:id"
                ),
                {"id": body.external_exercise_id},
            )
        )
        .mappings()
        .first()
    )
    if stored is None:
        try:
            exercise = await request.app.state.exercise_catalog.get_by_id(body.external_exercise_id)
        except ExerciseNotFoundError as error:
            raise problem(404, "not_found", "External exercise not found.") from error
        except ExerciseCatalogUnavailableError as error:
            raise problem(
                503, "catalog_unavailable", "The exercise catalog is temporarily unavailable."
            ) from error
        # The provider boundary stores only approved non-media display fields, never raw content.
        statement = insert_external(
            exercise.id,
            exercise.name,
            map_body_part(exercise.body_parts[0] if exercise.body_parts else None),
            map_equipment(exercise.equipment[0] if exercise.equipment else None),
        )
        await db.execute(statement)
        stored = (
            (
                await db.execute(
                    text(
                        "SELECT * FROM external_exercises WHERE provider='exercisedb' AND external_exercise_id=:id"
                    ),
                    {"id": body.external_exercise_id},
                )
            )
            .mappings()
            .one()
        )
    return {
        "source_kind": "external",
        "custom_exercise_id": None,
        "external_provider": "exercisedb",
        "external_exercise_id": stored["external_exercise_id"],
        "external_exercise_record_id": stored["id"],
        "exercise_name": stored["name"],
        "body_part": stored["body_part"],
        "equipment": stored["equipment"],
        "measurement_type": body.measurement_type,
        "note": body.note,
    }


def insert_external(external_id: str, name: str, body_part: str, equipment: str) -> Any:
    from sqlalchemy import column, table

    target = table(
        "external_exercises",
        column("provider"),
        column("external_exercise_id"),
        column("name"),
        column("body_part"),
        column("equipment"),
        column("attribution"),
        column("last_validated_at"),
    )
    statement = insert(target).values(
        provider="exercisedb",
        external_exercise_id=external_id,
        name=name[:120],
        body_part=body_part,
        equipment=equipment,
        attribution="ExerciseDB",
    )
    # Concurrent first selections converge on one shared provider record.
    return statement.on_conflict_do_update(
        index_elements=["provider", "external_exercise_id"],
        set_={"last_validated_at": text("now()")},
    )
