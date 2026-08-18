"""merge two heads

Revision ID: 5b532aa92a7b
Revises: 4c7d2a8e1f3b, 522a1ad33217
Create Date: 2026-07-01 17:28:08.049927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b532aa92a7b'
down_revision: Union[str, Sequence[str], None] = ('4c7d2a8e1f3b', '522a1ad33217')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
