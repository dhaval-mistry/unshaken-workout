"""Add user-owned exercises, reusable plans, and performed workouts.

Revision ID: 0002_workout_plans_and_sessions
Revises: 0001_database_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_workout_plans_and_sessions"
down_revision: str | None = "0001_database_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def _exercise_source_check() -> str:
    # A plan/session entry refers to one private exercise or one live vendor reference.
    return (
        "(source_kind = 'custom' AND custom_exercise_id IS NOT NULL "
        "AND external_provider IS NULL AND external_exercise_id IS NULL) OR "
        "(source_kind = 'external' AND custom_exercise_id IS NULL "
        "AND external_provider IS NOT NULL AND external_exercise_id IS NOT NULL)"
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _id(),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("preferred_weight_unit", sa.Text(), nullable=False, server_default="kg"),
        *_timestamps(),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="ck_users_display_name"),
        sa.CheckConstraint("length(trim(email)) > 0", name="ck_users_email"),
        sa.CheckConstraint("preferred_weight_unit IN ('kg', 'lb')", name="ck_users_weight_unit"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "custom_exercises",
        _id(),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("training_type", sa.Text(), nullable=False),
        sa.Column(
            "muscle_groups",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "equipment_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_custom_exercises_owner"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_custom_exercises_id_owner"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_custom_exercises_name"),
        sa.CheckConstraint(
            "training_type IN ('strength', 'functional', 'cardio', 'mobility', 'other')",
            name="ck_custom_exercises_training_type",
        ),
    )
    op.create_index("ix_custom_exercises_owner", "custom_exercises", ["owner_user_id"])

    op.create_table(
        "workout_plans",
        _id(),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_workout_plans_owner"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_workout_plans_id_owner"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_workout_plans_name"),
        sa.CheckConstraint("version > 0", name="ck_workout_plans_version"),
    )
    op.create_index("ix_workout_plans_owner", "workout_plans", ["owner_user_id"])

    op.create_table(
        "plan_exercises",
        _id(),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_order", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("custom_exercise_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_provider", sa.Text(), nullable=True),
        sa.Column("external_exercise_id", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["plan_id", "owner_user_id"],
            ["workout_plans.id", "workout_plans.owner_user_id"],
            name="fk_plan_exercises_plan_owner",
        ),
        sa.ForeignKeyConstraint(
            ["custom_exercise_id", "owner_user_id"],
            ["custom_exercises.id", "custom_exercises.owner_user_id"],
            name="fk_plan_exercises_custom_owner",
        ),
        sa.UniqueConstraint("plan_id", "exercise_order", name="uq_plan_exercises_order"),
        sa.CheckConstraint("exercise_order > 0", name="ck_plan_exercises_order"),
        sa.CheckConstraint(_exercise_source_check(), name="ck_plan_exercises_source"),
        sa.CheckConstraint(
            "external_provider IS NULL OR length(trim(external_provider)) > 0",
            name="ck_plan_exercises_provider",
        ),
        sa.CheckConstraint(
            "external_exercise_id IS NULL OR length(trim(external_exercise_id)) > 0",
            name="ck_plan_exercises_external_id",
        ),
    )

    op.create_table(
        "plan_sets",
        _id(),
        sa.Column("plan_exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight_kg", sa.Numeric(8, 2), nullable=True),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("target_distance_meters", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(
            ["plan_exercise_id"], ["plan_exercises.id"], name="fk_plan_sets_exercise"
        ),
        sa.UniqueConstraint("plan_exercise_id", "set_number", name="uq_plan_sets_number"),
        sa.CheckConstraint("set_number > 0", name="ck_plan_sets_number"),
        sa.CheckConstraint("target_reps IS NULL OR target_reps > 0", name="ck_plan_sets_reps"),
        sa.CheckConstraint(
            "target_weight_kg IS NULL OR target_weight_kg >= 0", name="ck_plan_sets_weight"
        ),
        sa.CheckConstraint(
            "target_duration_seconds IS NULL OR target_duration_seconds > 0",
            name="ck_plan_sets_duration",
        ),
        sa.CheckConstraint(
            "target_distance_meters IS NULL OR target_distance_meters > 0",
            name="ck_plan_sets_distance",
        ),
    )

    op.create_table(
        "workout_sessions",
        _id(),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="in_progress"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_time_seconds", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_workout_sessions_owner"),
        sa.ForeignKeyConstraint(
            ["source_plan_id", "owner_user_id"],
            ["workout_plans.id", "workout_plans.owner_user_id"],
            name="fk_workout_sessions_source_plan_owner",
        ),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_workout_sessions_id_owner"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'finished', 'abandoned')", name="ck_workout_sessions_status"
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_workout_sessions_time_order",
        ),
        sa.CheckConstraint(
            "(status = 'in_progress' AND finished_at IS NULL "
            "AND total_time_seconds IS NULL) OR "
            "(status IN ('finished', 'abandoned') AND finished_at IS NOT NULL "
            "AND total_time_seconds IS NOT NULL AND total_time_seconds >= 0)",
            name="ck_workout_sessions_completion",
        ),
    )
    op.create_index(
        "ix_workout_sessions_owner_started", "workout_sessions", ["owner_user_id", "started_at"]
    )

    op.create_table(
        "session_exercises",
        _id(),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_order", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("custom_exercise_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_provider", sa.Text(), nullable=True),
        sa.Column("external_exercise_id", sa.Text(), nullable=True),
        sa.Column("custom_name_at_start", sa.String(120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id", "owner_user_id"],
            ["workout_sessions.id", "workout_sessions.owner_user_id"],
            name="fk_session_exercises_session_owner",
        ),
        sa.ForeignKeyConstraint(
            ["custom_exercise_id", "owner_user_id"],
            ["custom_exercises.id", "custom_exercises.owner_user_id"],
            name="fk_session_exercises_custom_owner",
        ),
        sa.UniqueConstraint("session_id", "exercise_order", name="uq_session_exercises_order"),
        sa.CheckConstraint("exercise_order > 0", name="ck_session_exercises_order"),
        sa.CheckConstraint(_exercise_source_check(), name="ck_session_exercises_source"),
        sa.CheckConstraint(
            "external_provider IS NULL OR length(trim(external_provider)) > 0",
            name="ck_session_exercises_provider",
        ),
        sa.CheckConstraint(
            "external_exercise_id IS NULL OR length(trim(external_exercise_id)) > 0",
            name="ck_session_exercises_external_id",
        ),
        sa.CheckConstraint(
            "custom_name_at_start IS NULL OR source_kind = 'custom'",
            name="ck_session_exercises_custom_snapshot",
        ),
    )

    op.create_table(
        "session_sets",
        _id(),
        sa.Column("session_exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight_kg", sa.Numeric(8, 2), nullable=True),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("target_distance_meters", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("actual_weight_kg", sa.Numeric(8, 2), nullable=True),
        sa.Column("actual_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("actual_distance_meters", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_exercise_id"], ["session_exercises.id"], name="fk_session_sets_exercise"
        ),
        sa.UniqueConstraint("session_exercise_id", "set_number", name="uq_session_sets_number"),
        sa.CheckConstraint("set_number > 0", name="ck_session_sets_number"),
        sa.CheckConstraint(
            "target_reps IS NULL OR target_reps > 0", name="ck_session_sets_target_reps"
        ),
        sa.CheckConstraint(
            "actual_reps IS NULL OR actual_reps > 0", name="ck_session_sets_actual_reps"
        ),
        sa.CheckConstraint(
            "target_weight_kg IS NULL OR target_weight_kg >= 0",
            name="ck_session_sets_target_weight",
        ),
        sa.CheckConstraint(
            "actual_weight_kg IS NULL OR actual_weight_kg >= 0",
            name="ck_session_sets_actual_weight",
        ),
        sa.CheckConstraint(
            "target_duration_seconds IS NULL OR target_duration_seconds > 0",
            name="ck_session_sets_target_duration",
        ),
        sa.CheckConstraint(
            "actual_duration_seconds IS NULL OR actual_duration_seconds > 0",
            name="ck_session_sets_actual_duration",
        ),
        sa.CheckConstraint(
            "target_distance_meters IS NULL OR target_distance_meters > 0",
            name="ck_session_sets_target_distance",
        ),
        sa.CheckConstraint(
            "actual_distance_meters IS NULL OR actual_distance_meters > 0",
            name="ck_session_sets_actual_distance",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'completed', 'skipped')", name="ck_session_sets_status"
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_session_sets_completion",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR actual_reps IS NOT NULL OR "
            "actual_duration_seconds IS NOT NULL OR actual_distance_meters IS NOT NULL",
            name="ck_session_sets_completed_result",
        ),
    )


def downgrade() -> None:
    op.drop_table("session_sets")
    op.drop_table("session_exercises")
    op.drop_index("ix_workout_sessions_owner_started", table_name="workout_sessions")
    op.drop_table("workout_sessions")
    op.drop_table("plan_sets")
    op.drop_table("plan_exercises")
    op.drop_index("ix_workout_plans_owner", table_name="workout_plans")
    op.drop_table("workout_plans")
    op.drop_index("ix_custom_exercises_owner", table_name="custom_exercises")
    op.drop_table("custom_exercises")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
