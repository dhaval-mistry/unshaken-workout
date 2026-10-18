"""Add optimistic concurrency to workout sessions.

Revision ID: 0003_session_version
Revises: 0002_workout_plans_and_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_session_version"
down_revision: str | None = "0002_workout_plans_and_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workout_sessions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint("ck_workout_sessions_version", "workout_sessions", "version > 0")


def downgrade() -> None:
    op.drop_constraint("ck_workout_sessions_version", "workout_sessions", type_="check")
    op.drop_column("workout_sessions", "version")
