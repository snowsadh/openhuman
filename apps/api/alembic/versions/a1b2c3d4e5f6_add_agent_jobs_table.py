"""add agent_jobs table

Revision ID: a1b2c3d4e5f6
Revises: 0de87a911e11
Create Date: 2026-07-01 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "522a1ad33217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the agent_jobs table."""
    op.create_table(
        "agent_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column(
            "platform",
            sa.String(length=50),
            nullable=False,
            comment="slack | discord",
        ),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column(
            "thread_key",
            sa.String(length=500),
            nullable=False,
            comment="Stable conversation id: {platform}:{employee_id}:{channel_id}:{root_ts}",
        ),
        sa.Column(
            "job_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Tool arguments",
        ),
        sa.Column(
            "user_text",
            sa.Text(),
            nullable=True,
            comment="Original user message text",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "result_text",
            sa.Text(),
            nullable=True,
            comment="Worker-written result",
        ),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Worker-updated progress blob",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.CheckConstraint(
            "status IN ("
            "'pending','running','awaiting_approval','succeeded','failed','cancelled'"
            ")",
            name="ck_agent_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes
    op.create_index(
        "ix_agent_jobs_thread_key", "agent_jobs", ["thread_key"], unique=False
    )
    op.create_index(
        "ix_agent_jobs_status", "agent_jobs", ["status"], unique=False
    )
    op.create_index(
        "ix_agent_jobs_job_type", "agent_jobs", ["job_type"], unique=False
    )
    op.create_index(
        "ix_agent_jobs_employee_id", "agent_jobs", ["employee_id"], unique=False
    )


def downgrade() -> None:
    """Drop the agent_jobs table."""
    op.drop_index("ix_agent_jobs_employee_id", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_job_type", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_status", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_thread_key", table_name="agent_jobs")
    op.execute("DROP TABLE IF EXISTS agent_jobs CASCADE")
