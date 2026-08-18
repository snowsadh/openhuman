"""add sales to employee_type check constraint

Revision ID: 60e6617d105f
Revises: ef7cebf449fe
Create Date: 2026-07-05 07:35:00.000000

The 'sales' employee type was added to the model/schema layer but the
database CHECK constraint created in 522a1ad33217 was never updated,
so creating a sales employee ("Marcus") always failed with an unhandled
CheckViolationError (surfaced to the browser as a CORS error, since
Starlette can't attach CORS headers to a response after an unhandled
exception has already unwound past the middleware).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '60e6617d105f'
down_revision: Union[str, Sequence[str], None] = 'ef7cebf449fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_employees_employee_type', 'employees', type_='check')
    op.create_check_constraint(
        'ck_employees_employee_type',
        'employees',
        "employee_type IS NULL OR employee_type IN "
        "('legal-compliance', 'support', 'hr', 'general', 'sales')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_employees_employee_type', 'employees', type_='check')
    op.create_check_constraint(
        'ck_employees_employee_type',
        'employees',
        "employee_type IS NULL OR employee_type IN "
        "('legal-compliance', 'support', 'hr', 'general')",
    )
