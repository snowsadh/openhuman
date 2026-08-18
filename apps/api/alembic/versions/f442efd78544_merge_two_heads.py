"""merge two heads

Revision ID: f442efd78544
Revises: 8c3855eb11a5, f7a1b2c3d4e5
Create Date: 2026-07-03 14:08:58.730532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f442efd78544'
down_revision: Union[str, Sequence[str], None] = ('8c3855eb11a5', 'f7a1b2c3d4e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
