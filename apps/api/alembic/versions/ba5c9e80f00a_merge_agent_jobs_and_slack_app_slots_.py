"""merge agent_jobs and slack_app_slots branches

Revision ID: ba5c9e80f00a
Revises: 0de87a911e11, a1b2c3d4e5f6
Create Date: 2026-07-01 22:05:38.896716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba5c9e80f00a'
down_revision: Union[str, Sequence[str], None] = ('0de87a911e11', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
