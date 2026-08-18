"""add_password_hash_nullable_clerk_id

Revision ID: c1e8a8dc94fe
Revises: 8c3855eb11a5
Create Date: 2026-07-04 20:49:48.370158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1e8a8dc94fe'
down_revision: Union[str, Sequence[str], None] = '8c3855eb11a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add password_hash column and make clerk_id nullable."""
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.alter_column('users', 'clerk_id', nullable=True)


def downgrade() -> None:
    """Remove password_hash and make clerk_id non-nullable."""
    op.alter_column('users', 'clerk_id', nullable=False)
    op.drop_column('users', 'password_hash')
