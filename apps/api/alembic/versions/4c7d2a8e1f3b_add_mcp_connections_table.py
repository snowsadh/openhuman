"""add mcp_connections table

Revision ID: 4c7d2a8e1f3b
Revises: 3b3f34b263c7
Create Date: 2026-07-01 11:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4c7d2a8e1f3b"
down_revision: str | Sequence[str] | None = "3b3f34b263c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the mcp_connections table."""
    op.create_table(
        "mcp_connections",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column(
            "employee_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL = org-wide connection available to all employees",
        ),
        sa.Column(
            "connector_slug",
            sa.String(length=100),
            nullable=False,
            comment="Matches a key in the connector REGISTRY",
        ),
        sa.Column(
            "auth_type",
            sa.String(length=50),
            nullable=False,
            comment="none | api_key_header | pat_bearer | oauth2",
        ),
        sa.Column(
            "credentials_enc",
            sa.Text(),
            nullable=True,
            comment="Encrypted API key, PAT, or OAuth access token",
        ),
        sa.Column(
            "oauth_refresh_token_enc",
            sa.Text(),
            nullable=True,
            comment="Encrypted OAuth2 refresh token",
        ),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Granted OAuth scopes (or configured scopes)",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="connected",
            nullable=False,
        ),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Constraints
        sa.CheckConstraint(
            "status IN ('connected', 'error', 'revoked')",
            name="ck_mcp_connections_status",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes
    op.create_index(
        "ix_mcp_connections_org_id", "mcp_connections", ["org_id"], unique=False
    )
    op.create_index(
        "ix_mcp_connections_employee_id",
        "mcp_connections",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_connections_org_slug",
        "mcp_connections",
        ["org_id", "connector_slug"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the mcp_connections table."""
    op.drop_index("ix_mcp_connections_org_slug", table_name="mcp_connections")
    op.drop_index("ix_mcp_connections_employee_id", table_name="mcp_connections")
    op.drop_index("ix_mcp_connections_org_id", table_name="mcp_connections")
    op.execute("DROP TABLE IF EXISTS mcp_connections CASCADE")
