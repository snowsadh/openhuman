"""merge_jwt_auth_and_onboarding

Revision ID: ef7cebf449fe
Revises: c1e8a8dc94fe, 3a9013c04672
Create Date: 2026-07-04 21:23:03.126582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef7cebf449fe'
down_revision: Union[str, Sequence[str], None] = ('c1e8a8dc94fe', '3a9013c04672')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
