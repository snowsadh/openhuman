"""add ArmorIQ approval governance tables

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_assignments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("approver_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "agent_type IN ('hr','sales','support','general','legal-compliance')",
            name="ck_approval_assignment_agent_type",
        ),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "agent_type", name="uq_approval_assignment_org_role"),
    )
    op.create_index("ix_approval_assignments_org_id", "approval_assignments", ["org_id"])
    op.create_index(
        "ix_approval_assignments_approver_user_id",
        "approval_assignments",
        ["approver_user_id"],
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("plan_hash", sa.String(length=128), nullable=False),
        sa.Column("token_id", sa.String(length=255), nullable=True),
        sa.Column("delegation_id", sa.String(length=255), nullable=True),
        sa.Column("mcp", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("redacted_parameters", postgresql.JSONB(), nullable=False),
        sa.Column("requester_email", sa.String(length=320), nullable=True),
        sa.Column("assigned_approver_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("armoriq_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','expired','executed','failed')",
            name="ck_approval_requests_status",
        ),
        sa.ForeignKeyConstraint(["assigned_approver_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org_id", "plan_hash", "mcp", "action", name="uq_approval_request_plan_action"
        ),
    )
    for column in (
        "org_id",
        "employee_id",
        "job_id",
        "plan_hash",
        "delegation_id",
        "mcp",
        "action",
        "assigned_approver_id",
        "status",
    ):
        op.create_index(f"ix_approval_requests_{column}", "approval_requests", [column])
    op.create_index(
        "ix_approval_requests_org_status_created",
        "approval_requests",
        ["org_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_table("approval_assignments")
