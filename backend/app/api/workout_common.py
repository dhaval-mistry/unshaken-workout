"""Shared SQL and HTTP helpers for owner-scoped workout resources."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def problem(http_status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def require_fields(fields: set[str]) -> None:
    if not fields:
        raise problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "At least one field is required.",
        )


def parse_version(if_match: str | None) -> int:
    if if_match is None:
        raise problem(
            status.HTTP_428_PRECONDITION_REQUIRED, "version_required", "If-Match is required."
        )
    value = if_match.strip()
    if len(value) < 3 or value[0] != '"' or value[-1] != '"' or not value[1:-1].isdigit():
        raise problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_version",
            "If-Match must be a quoted integer.",
        )
    return int(value[1:-1])


async def optional_if_match(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> str | None:
    """Let service code return the contract's explicit 428 for a missing precondition."""

    return if_match


def etag(version: int) -> dict[str, str]:
    return {"ETag": f'"{version}"'}


def clean_row(row: Any) -> dict[str, Any]:
    return dict(row)


async def lock_parent(
    db: AsyncSession, table: str, resource_id: UUID, owner_id: UUID, expected: int
) -> Any:
    if table not in {"workout_plans", "workout_sessions"}:
        raise ValueError("unsupported versioned table")
    row = (
        (
            await db.execute(
                text(f"SELECT * FROM {table} WHERE id=:id AND owner_user_id=:owner FOR UPDATE"),
                {"id": resource_id, "owner": owner_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise problem(404, "not_found", "Resource not found.")
    if row["version"] != expected:
        raise problem(409, "version_conflict", "The resource was changed by another request.")
    return row


async def bump_version(db: AsyncSession, table: str, resource_id: UUID) -> int:
    row = (
        await db.execute(
            text(
                f"UPDATE {table} SET version=version+1, updated_at=now() WHERE id=:id RETURNING version"
            ),
            {"id": resource_id},
        )
    ).first()
    assert row is not None
    return int(row[0])


async def compact_numbers(
    db: AsyncSession, table: str, parent_column: str, parent_id: UUID, number_column: str
) -> None:
    allowed = {
        ("plan_exercises", "plan_id", "exercise_order"),
        ("session_exercises", "session_id", "exercise_order"),
        ("plan_sets", "plan_exercise_id", "set_number"),
        ("session_sets", "session_exercise_id", "set_number"),
    }
    if (table, parent_column, number_column) not in allowed:
        raise ValueError("unsupported ordering target")
    # A high temporary offset avoids both unique collisions and positive-number checks.
    await db.execute(
        text(
            f"UPDATE {table} SET {number_column}={number_column}+10000 WHERE {parent_column}=:parent"
        ),
        {"parent": parent_id},
    )
    await db.execute(
        text(
            f"""WITH ranked AS (
            SELECT id, row_number() OVER (ORDER BY {number_column}) AS new_number
            FROM {table} WHERE {parent_column}=:parent
            ) UPDATE {table} t SET {number_column}=ranked.new_number
            FROM ranked WHERE t.id=ranked.id"""
        ),
        {"parent": parent_id},
    )
