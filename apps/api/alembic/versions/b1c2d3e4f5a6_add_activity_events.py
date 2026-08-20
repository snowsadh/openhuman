"""add activity_events table

Revision ID: b1c2d3e4f5a6
Revises: a1147141b092
Create Date: 2026-07-04 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a1147141b092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the activity_events table."""
    op.create_table(
        "activity_events",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="JSON string for expandable detail",
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column(
            "employee_name",
            sa.String(length=255),
            nullable=True,
            comment="Denormalized for query speed",
        ),
        sa.Column(
            "platform",
            sa.String(length=50),
            nullable=True,
            comment="slack | discord | api",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=True,
            comment="succeeded | failed | pending | ...",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Extra structured payload",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes
    op.create_index(
        "ix_activity_events_org_id", "activity_events", ["org_id"], unique=False
    )
    op.create_index(
        "ix_activity_events_event_type",
        "activity_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_occurred_at",
        "activity_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_employee_id",
        "activity_events",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_activity_events_org_occurred",
        "activity_events",
        ["org_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the activity_events table."""
    op.drop_index("ix_activity_events_org_occurred", table_name="activity_events")
    op.drop_index("ix_activity_events_employee_id", table_name="activity_events")
    op.drop_index("ix_activity_events_occurred_at", table_name="activity_events")
    op.drop_index("ix_activity_events_event_type", table_name="activity_events")
    op.drop_index("ix_activity_events_org_id", table_name="activity_events")
    op.execute("DROP TABLE IF EXISTS activity_events CASCADE")
