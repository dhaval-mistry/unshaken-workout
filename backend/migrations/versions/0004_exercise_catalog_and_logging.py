# ruff: noqa: E501
"""Add selected external exercises and measurement-aware workout logging.

Downgrade recreates legacy arrays from the retained single taxonomy values. Any
additional legacy array values discarded during upgrade cannot be recovered.

Revision ID: 0004_exercise_catalog
Revises: 0003_session_version
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_exercise_catalog"
down_revision: str | None = "0003_session_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EQUIPMENT = "('barbell','dumbbell','kettlebell','resistance_band','cable','machine','bodyweight','cardio_machine','medicine_ball','suspension_trainer','other')"
BODY_PARTS = "('full_body','chest','back','shoulders','arms','core','glutes','legs','calves','cardio','mobility','other')"


def upgrade() -> None:
    op.create_table(
        "external_exercises",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_exercise_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("body_part", sa.Text(), nullable=False),
        sa.Column("equipment", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column(
            "first_selected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_validated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "provider", "external_exercise_id", name="uq_external_exercises_provider_id"
        ),
        sa.CheckConstraint("provider = 'exercisedb'", name="ck_external_exercises_provider"),
        sa.CheckConstraint(
            "length(trim(external_exercise_id)) BETWEEN 1 AND 100", name="ck_external_exercises_id"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_external_exercises_name"),
        sa.CheckConstraint(f"body_part IN {BODY_PARTS}", name="ck_external_exercises_body_part"),
        sa.CheckConstraint(f"equipment IN {EQUIPMENT}", name="ck_external_exercises_equipment"),
    )
    op.create_index(
        "ix_external_exercises_name",
        "external_exercises",
        [sa.text("lower(name)"), "provider", "external_exercise_id"],
    )

    for name in ("equipment", "body_part", "measurement_type"):
        op.add_column("custom_exercises", sa.Column(name, sa.Text(), nullable=True))
    # Multiple, missing, and unknown legacy classifications intentionally collapse to other.
    op.execute(f"""UPDATE custom_exercises SET
      equipment = CASE WHEN cardinality(equipment_types)=1 AND equipment_types[1] IN {EQUIPMENT} THEN equipment_types[1] ELSE 'other' END,
      body_part = CASE WHEN cardinality(muscle_groups)=1 AND muscle_groups[1] IN {BODY_PARTS} THEN muscle_groups[1] ELSE 'other' END,
      measurement_type='reps'""")
    for name in ("equipment", "body_part", "measurement_type"):
        op.alter_column("custom_exercises", name, nullable=False)
    op.create_check_constraint(
        "ck_custom_exercises_equipment", "custom_exercises", f"equipment IN {EQUIPMENT}"
    )
    op.create_check_constraint(
        "ck_custom_exercises_body_part", "custom_exercises", f"body_part IN {BODY_PARTS}"
    )
    op.create_check_constraint(
        "ck_custom_exercises_measurement",
        "custom_exercises",
        "measurement_type IN ('reps','duration')",
    )
    op.drop_column("custom_exercises", "equipment_types")
    op.drop_column("custom_exercises", "muscle_groups")
    op.create_index(
        "ix_custom_exercises_owner_name",
        "custom_exercises",
        ["owner_user_id", sa.text("lower(name)"), "id"],
    )

    for table in ("plan_exercises", "session_exercises"):
        op.add_column(
            table,
            sa.Column("external_exercise_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.add_column(table, sa.Column("exercise_name", sa.String(120), nullable=True))
        op.add_column(table, sa.Column("body_part", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("equipment", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("measurement_type", sa.Text(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_external_record",
            table,
            "external_exercises",
            ["external_exercise_record_id"],
            ["id"],
        )
        op.drop_constraint(f"ck_{table}_source", table, type_="check")
        op.execute(f"""UPDATE {table} x SET exercise_name=c.name, body_part=c.body_part,
          equipment=c.equipment, measurement_type=c.measurement_type FROM custom_exercises c
          WHERE x.source_kind='custom' AND x.custom_exercise_id=c.id AND x.owner_user_id=c.owner_user_id""")
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table} WHERE exercise_name IS NULL) THEN
          RAISE EXCEPTION 'cannot migrate unresolved external or invalid exercise occurrence in {table}'; END IF; END $$""")
        for name in ("exercise_name", "body_part", "equipment", "measurement_type"):
            op.alter_column(table, name, nullable=False)
        op.create_check_constraint(f"ck_{table}_body_part", table, f"body_part IN {BODY_PARTS}")
        op.create_check_constraint(f"ck_{table}_equipment", table, f"equipment IN {EQUIPMENT}")
        op.create_check_constraint(
            f"ck_{table}_measurement", table, "measurement_type IN ('reps','duration')"
        )
        op.create_check_constraint(
            f"ck_{table}_source",
            table,
            "(source_kind='custom' AND custom_exercise_id IS NOT NULL AND external_provider IS NULL AND external_exercise_id IS NULL AND external_exercise_record_id IS NULL) OR "
            "(source_kind='external' AND custom_exercise_id IS NULL AND external_provider='exercisedb' AND external_exercise_id IS NOT NULL AND external_exercise_record_id IS NOT NULL)",
        )
        op.create_unique_constraint(f"uq_{table}_id_measurement", table, ["id", "measurement_type"])

    op.drop_constraint("ck_session_exercises_custom_snapshot", "session_exercises", type_="check")
    op.drop_column("session_exercises", "custom_name_at_start")

    for table, parent, old_fk, exercise_column in (
        ("plan_sets", "plan_exercises", "fk_plan_sets_exercise", "plan_exercise_id"),
        ("session_sets", "session_exercises", "fk_session_sets_exercise", "session_exercise_id"),
    ):
        op.add_column(table, sa.Column("measurement_type", sa.Text(), nullable=True))
        op.add_column(
            table, sa.Column("rest_seconds", sa.Integer(), nullable=False, server_default="120")
        )
        op.execute(f"UPDATE {table} SET measurement_type='reps'")
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table} WHERE target_reps IS NULL) THEN
          RAISE EXCEPTION 'cannot migrate set without target repetitions in {table}'; END IF; END $$""")
        op.alter_column(table, "measurement_type", nullable=False)
        op.drop_constraint(old_fk, table, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table}_exercise_measurement",
            table,
            parent,
            [exercise_column, "measurement_type"],
            ["id", "measurement_type"],
            ondelete="CASCADE",
        )
        op.create_check_constraint(f"ck_{table}_rest", table, "rest_seconds BETWEEN 0 AND 3600")
        op.create_check_constraint(
            f"ck_{table}_measurement", table, "measurement_type IN ('reps','duration')"
        )
        op.drop_column(table, "target_distance_meters")
    op.drop_column("session_sets", "actual_distance_meters")

    for constraint in ("ck_plan_sets_reps", "ck_plan_sets_duration"):
        op.drop_constraint(constraint, "plan_sets", type_="check")
    op.create_check_constraint(
        "ck_plan_sets_target",
        "plan_sets",
        "(measurement_type='reps' AND target_reps IS NOT NULL AND target_reps BETWEEN 1 AND 999 AND target_duration_seconds IS NULL) OR (measurement_type='duration' AND target_reps IS NULL AND target_duration_seconds IS NOT NULL AND target_duration_seconds BETWEEN 1 AND 86400)",
    )
    for constraint in (
        "ck_session_sets_target_reps",
        "ck_session_sets_actual_reps",
        "ck_session_sets_target_duration",
        "ck_session_sets_actual_duration",
        "ck_session_sets_completion",
    ):
        op.drop_constraint(constraint, "session_sets", type_="check")
    op.create_check_constraint(
        "ck_session_sets_target",
        "session_sets",
        "(measurement_type='reps' AND target_reps IS NOT NULL AND target_reps BETWEEN 1 AND 999 AND target_duration_seconds IS NULL) OR (measurement_type='duration' AND target_reps IS NULL AND target_duration_seconds IS NOT NULL AND target_duration_seconds BETWEEN 1 AND 86400)",
    )
    op.create_check_constraint(
        "ck_session_sets_results",
        "session_sets",
        "(status IN ('planned','skipped') AND actual_reps IS NULL AND actual_duration_seconds IS NULL AND actual_weight_kg IS NULL AND completed_at IS NULL) OR (status='completed' AND completed_at IS NOT NULL AND ((measurement_type='reps' AND actual_reps IS NOT NULL AND actual_reps BETWEEN 1 AND 999 AND actual_duration_seconds IS NULL) OR (measurement_type='duration' AND actual_reps IS NULL AND actual_duration_seconds IS NOT NULL AND actual_duration_seconds BETWEEN 1 AND 86400)))",
    )

    op.drop_constraint(
        "fk_session_exercises_session_owner", "session_exercises", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_session_exercises_session_owner",
        "session_exercises",
        "workout_sessions",
        ["session_id", "owner_user_id"],
        ["id", "owner_user_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_workout_sessions_one_active",
        "workout_sessions",
        ["owner_user_id"],
        unique=True,
        postgresql_where=sa.text("status='in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("uq_workout_sessions_one_active", table_name="workout_sessions")
    op.drop_constraint(
        "fk_session_exercises_session_owner", "session_exercises", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_session_exercises_session_owner",
        "session_exercises",
        "workout_sessions",
        ["session_id", "owner_user_id"],
        ["id", "owner_user_id"],
    )
    op.add_column(
        "session_sets", sa.Column("actual_distance_meters", sa.Numeric(10, 2), nullable=True)
    )
    for table, parent, col in (
        ("session_sets", "session_exercises", "session_exercise_id"),
        ("plan_sets", "plan_exercises", "plan_exercise_id"),
    ):
        op.add_column(table, sa.Column("target_distance_meters", sa.Numeric(10, 2), nullable=True))
        op.drop_constraint(f"fk_{table}_exercise_measurement", table, type_="foreignkey")
        op.create_foreign_key(
            "fk_session_sets_exercise" if table == "session_sets" else "fk_plan_sets_exercise",
            table,
            parent,
            [col],
            ["id"],
        )
        op.drop_column(table, "rest_seconds")
        op.drop_column(table, "measurement_type")
    op.create_check_constraint(
        "ck_plan_sets_reps", "plan_sets", "target_reps IS NULL OR target_reps > 0"
    )
    op.create_check_constraint(
        "ck_plan_sets_duration",
        "plan_sets",
        "target_duration_seconds IS NULL OR target_duration_seconds > 0",
    )
    op.create_check_constraint(
        "ck_plan_sets_distance",
        "plan_sets",
        "target_distance_meters IS NULL OR target_distance_meters > 0",
    )
    for name, expression in (
        ("ck_session_sets_target_reps", "target_reps IS NULL OR target_reps > 0"),
        ("ck_session_sets_actual_reps", "actual_reps IS NULL OR actual_reps > 0"),
        (
            "ck_session_sets_target_duration",
            "target_duration_seconds IS NULL OR target_duration_seconds > 0",
        ),
        (
            "ck_session_sets_actual_duration",
            "actual_duration_seconds IS NULL OR actual_duration_seconds > 0",
        ),
        (
            "ck_session_sets_target_distance",
            "target_distance_meters IS NULL OR target_distance_meters > 0",
        ),
        (
            "ck_session_sets_actual_distance",
            "actual_distance_meters IS NULL OR actual_distance_meters > 0",
        ),
        (
            "ck_session_sets_completion",
            "(status = 'completed' AND completed_at IS NOT NULL) OR (status <> 'completed' AND completed_at IS NULL)",
        ),
        (
            "ck_session_sets_completed_result",
            "status <> 'completed' OR actual_reps IS NOT NULL OR actual_duration_seconds IS NOT NULL OR actual_distance_meters IS NOT NULL",
        ),
    ):
        op.create_check_constraint(name, "session_sets", expression)
    op.add_column(
        "session_exercises", sa.Column("custom_name_at_start", sa.String(120), nullable=True)
    )
    op.execute(
        "UPDATE session_exercises SET custom_name_at_start=exercise_name WHERE source_kind='custom'"
    )
    for table in ("session_exercises", "plan_exercises"):
        op.drop_constraint(f"fk_{table}_external_record", table, type_="foreignkey")
        for name in (
            "external_exercise_record_id",
            "exercise_name",
            "body_part",
            "equipment",
            "measurement_type",
        ):
            op.drop_column(table, name)
        op.create_check_constraint(
            f"ck_{table}_source",
            table,
            "(source_kind = 'custom' AND custom_exercise_id IS NOT NULL AND external_provider IS NULL AND external_exercise_id IS NULL) OR "
            "(source_kind = 'external' AND custom_exercise_id IS NULL AND external_provider IS NOT NULL AND external_exercise_id IS NOT NULL)",
        )
    op.create_check_constraint(
        "ck_session_exercises_custom_snapshot",
        "session_exercises",
        "custom_name_at_start IS NULL OR source_kind = 'custom'",
    )
    op.drop_index("ix_custom_exercises_owner_name", table_name="custom_exercises")
    op.add_column(
        "custom_exercises",
        sa.Column(
            "muscle_groups",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "custom_exercises",
        sa.Column(
            "equipment_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.execute(
        "UPDATE custom_exercises SET muscle_groups=ARRAY[body_part], equipment_types=ARRAY[equipment]"
    )
    for name in ("measurement_type", "body_part", "equipment"):
        op.drop_column("custom_exercises", name)
    op.drop_index("ix_external_exercises_name", table_name="external_exercises")
    op.drop_table("external_exercises")
