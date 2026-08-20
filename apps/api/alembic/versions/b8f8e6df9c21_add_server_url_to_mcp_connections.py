"""add server_url to mcp_connections

Revision ID: b8f8e6df9c21
Revises: 8c3855eb11a5
Create Date: 2026-07-05 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8f8e6df9c21"
down_revision = "60e6617d105f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_connections",
        sa.Column(
            "server_url",
            sa.String(length=1000),
            nullable=True,
            comment="Optional per-connection MCP server URL override",
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_connections", "server_url")
