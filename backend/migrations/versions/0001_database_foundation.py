"""Establish migration history before approved domain tables are introduced.

Revision ID: 0001_database_foundation
Revises:
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_database_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record the baseline; feature tables require separately approved migrations."""


def downgrade() -> None:
    """The baseline has no schema objects to remove."""
