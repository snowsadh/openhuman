"""add durable employee schedules

Revision ID: c8d9e0f1a2b3
Revises: b8f8e6df9c21
"""
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from croniter import croniter

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b8f8e6df9c21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_schedules",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(100), server_default="UTC", nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("channel_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','paused')", name="ck_employee_schedules_status"),
        sa.CheckConstraint("platform IN ('slack','discord')", name="ck_employee_schedules_platform"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_schedules_org_id", "employee_schedules", ["org_id"])
    op.create_index("ix_employee_schedules_employee_id", "employee_schedules", ["employee_id"])
    op.create_index("ix_employee_schedules_next_run_at", "employee_schedules", ["next_run_at"])

    op.add_column("agent_jobs", sa.Column("schedule_id", sa.Uuid(), nullable=True))
    op.add_column("agent_jobs", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_jobs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_jobs", sa.Column("attempt", sa.Integer(), server_default="0", nullable=False))
    op.add_column("agent_jobs", sa.Column("delivery_status", sa.String(50), nullable=True))
    op.add_column("agent_jobs", sa.Column("delivery_error", sa.Text(), nullable=True))
    op.add_column("agent_jobs", sa.Column("lease_owner", sa.String(100), nullable=True))
    op.add_column("agent_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_agent_jobs_schedule_id", "agent_jobs", "employee_schedules",
        ["schedule_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_agent_jobs_schedule_id", "agent_jobs", ["schedule_id"])
    op.create_index("ix_agent_jobs_scheduled_for", "agent_jobs", ["scheduled_for"])
    op.create_index("ix_agent_jobs_available_at", "agent_jobs", ["available_at"])
    op.create_index("ix_agent_jobs_lease_owner", "agent_jobs", ["lease_owner"])
    op.create_index("ix_agent_jobs_lease_expires_at", "agent_jobs", ["lease_expires_at"])
    op.create_unique_constraint(
        "uq_agent_jobs_schedule_occurrence", "agent_jobs", ["schedule_id", "scheduled_for"]
    )

    # Convert legacy cron-definition rows before disabling them. Older code
    # stored definitions in the execution queue and the worker often marked
    # them failed immediately because no handler existed.
    bind = op.get_bind()
    legacy_rows = bind.execute(sa.text("""
        SELECT j.id, j.employee_id, j.platform, j.channel_id, j.payload, e.org_id
        FROM agent_jobs j
        JOIN employees e ON e.id = j.employee_id
        WHERE j.job_type = 'cronjob'
    """)).mappings()
    for row in legacy_rows:
        payload = row["payload"] or {}
        expression = payload.get("schedule")
        prompt = payload.get("prompt")
        if (
            not expression
            or not prompt
            or not croniter.is_valid(expression)
            or row["platform"] not in ("slack", "discord")
        ):
            continue
        next_run = croniter(expression, datetime.now(UTC)).get_next(datetime)
        bind.execute(sa.text("""
            INSERT INTO employee_schedules
                (id, org_id, employee_id, name, prompt, cron_expression, timezone,
                 platform, channel_id, status, next_run_at, created_at)
            VALUES
                (:id, :org_id, :employee_id, :name, :prompt, :expression, 'UTC',
                 :platform, :channel_id, :status, :next_run, now())
        """), {
            "id": uuid4(),
            "org_id": row["org_id"],
            "employee_id": row["employee_id"],
            "name": payload.get("name") or "Migrated schedule",
            "prompt": prompt,
            "expression": expression,
            "platform": row["platform"],
            "channel_id": row["channel_id"],
            "status": "paused" if payload.get("paused") else "active",
            "next_run": next_run,
        })

    op.execute("""
        UPDATE agent_jobs
        SET status = 'cancelled',
            error = COALESCE(error, 'Legacy cron definition disabled during schedule migration'),
            finished_at = COALESCE(finished_at, now())
        WHERE job_type = 'cronjob' AND status IN ('pending','running','awaiting_approval')
    """)


def downgrade() -> None:
    op.drop_constraint("uq_agent_jobs_schedule_occurrence", "agent_jobs", type_="unique")
    op.drop_index("ix_agent_jobs_available_at", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_scheduled_for", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_schedule_id", table_name="agent_jobs")
    op.drop_constraint("fk_agent_jobs_schedule_id", "agent_jobs", type_="foreignkey")
    op.drop_index("ix_agent_jobs_lease_expires_at", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_lease_owner", table_name="agent_jobs")
    for column in ("lease_expires_at", "lease_owner", "delivery_error", "delivery_status", "attempt", "available_at", "scheduled_for", "schedule_id"):
        op.drop_column("agent_jobs", column)
    op.drop_index("ix_employee_schedules_next_run_at", table_name="employee_schedules")
    op.drop_index("ix_employee_schedules_employee_id", table_name="employee_schedules")
    op.drop_index("ix_employee_schedules_org_id", table_name="employee_schedules")
    op.drop_table("employee_schedules")
