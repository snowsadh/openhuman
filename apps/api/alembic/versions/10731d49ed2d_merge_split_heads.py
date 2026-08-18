"""merge split heads

Revision ID: 10731d49ed2d
Revises: 5b532aa92a7b, e7f8a9b0c1d2
Create Date: 2026-07-02 17:26:13.589476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10731d49ed2d'
down_revision: Union[str, Sequence[str], None] = ('5b532aa92a7b', 'e7f8a9b0c1d2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
