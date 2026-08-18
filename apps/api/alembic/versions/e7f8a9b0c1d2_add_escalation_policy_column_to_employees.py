"""add escalation_policy column to employees

Revision ID: e7f8a9b0c1d2
Revises: ba5c9e80f00a
Create Date: 2026-07-01 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "ba5c9e80f00a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add escalation_policy JSONB column to employees table."""
    op.add_column(
        "employees",
        sa.Column("escalation_policy", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove escalation_policy column from employees table."""
    op.drop_column("employees", "escalation_policy")
