"""initial schema

Revision ID: 3b3f34b263c7
Revises:
Create Date: 2026-06-30 19:09:38.478305
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3b3f34b263c7"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Phase 1 schema without dropping pre-existing data."""
    # Create tables in FK order.
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cognee_tenant_id", sa.String(length=255), nullable=True),
        sa.Column("cognee_tenant_name", sa.String(length=255), nullable=True),
        sa.Column("cognee_system_user_id", sa.String(length=255), nullable=True),
        sa.Column("cognee_system_user_name", sa.String(length=255), nullable=True),
        sa.Column("cognee_dataset_id", sa.String(length=255), nullable=True),
        sa.Column("cognee_dataset_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"], unique=False)

    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("personality", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("specialization", sa.String(length=255), nullable=True),
        sa.Column("duties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discord_token_enc", sa.Text(), nullable=True),
        sa.Column("slack_token_enc", sa.Text(), nullable=True),
        sa.Column("mcp_connections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("memory_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cognee_user_id", sa.String(length=255), nullable=True),
        sa.Column("cognee_user_name", sa.String(length=255), nullable=True),
        sa.Column("cognee_dataset_id", sa.String(length=255), nullable=True),
        sa.Column("cognee_dataset_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="inactive", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_employees_status",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employees_org_id", "employees", ["org_id"], unique=False)

    op.create_table(
        "channel_assignments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id",
            "platform",
            "channel_id",
            name="uq_channel_assignments_employee_platform_channel",
        ),
    )
    op.create_index(
        "ix_channel_assignments_employee_id",
        "channel_assignments",
        ["employee_id"],
        unique=False,
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("cognee_document_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="uploaded", nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'indexed', 'failed')",
            name="ck_documents_status",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_employee_id", "documents", ["employee_id"], unique=False)
    op.create_index("ix_documents_org_id", "documents", ["org_id"], unique=False)


def downgrade() -> None:
    """Drop all tables in reverse FK order."""
    op.drop_index("ix_documents_org_id", table_name="documents")
    op.drop_index("ix_documents_employee_id", table_name="documents")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS channel_assignments CASCADE")
    op.execute("DROP TABLE IF EXISTS employees CASCADE")
    op.drop_index("ix_organizations_owner_id", table_name="organizations")
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
