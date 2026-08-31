"""add MCP connection verification metadata

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_connections",
        sa.Column(
            "verification_status",
            sa.String(length=50),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.add_column("mcp_connections", sa.Column("discovered_tools", sa.JSON(), nullable=True))
    op.add_column(
        "mcp_connections",
        sa.Column("discovered_tool_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("mcp_connections", sa.Column("verification_error", sa.Text(), nullable=True))
    op.add_column(
        "mcp_connections",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mcp_connections",
        sa.Column("oauth_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_mcp_connections_verification_status",
        "mcp_connections",
        "verification_status IN ('unverified', 'discovered', 'verified', 'error')",
    )
    op.create_index(
        "ix_mcp_connections_org_verification",
        "mcp_connections",
        ["org_id", "verification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_connections_org_verification", table_name="mcp_connections")
    op.drop_constraint(
        "ck_mcp_connections_verification_status",
        "mcp_connections",
        type_="check",
    )
    for column in (
        "oauth_expires_at",
        "last_verified_at",
        "verification_error",
        "discovered_tool_count",
        "discovered_tools",
        "verification_status",
    ):
        op.drop_column("mcp_connections", column)
