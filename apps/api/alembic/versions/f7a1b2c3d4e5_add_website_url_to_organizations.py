"""add website_url to organizations

Revision ID: f7a1b2c3d4e5
Revises: e7f8a9b0c1d2
Create Date: 2026-07-02 00:35:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("website_url", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "website_url")
