#!/usr/bin/env python3
"""
Backfill Cognee memory provisioning for employees where it previously failed.

Root cause (fixed in app/memory/service.py): `create_employee_user()` derived
a deterministic email from (tenant_id, employee_name) but always called
`create_user()` instead of checking for an existing user first. If an employee
was deleted and later recreated with the same name in the same org (or a
request was retried), the Cognee user already existed and `create_user()`
raised `UserAlreadyExists`. That exception was swallowed as "non-blocking" by
`create_employee()`, leaving `cognee_user_id` / `cognee_dataset_id` unset on
the employee row — which is why the employee's memory system reports as "not
set up" even though the employee itself was created successfully.

This script finds employees with a provisioned org (org.cognee_tenant_id set)
but missing Cognee fields, and re-runs provisioning for them using the now
idempotent `create_employee_user()`.

Usage:
    python -m scripts.backfill_cognee_employees            # apply
    python -m scripts.backfill_cognee_employees --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

# Import all model modules FIRST so SQLAlchemy can resolve relationship
# strings before mapper configuration runs (mirrors app/main.py).
import app.auth.models  # noqa: F401,E402
import app.channel_assignments.models  # noqa: F401,E402
import app.documents.models  # noqa: F401,E402
import app.organizations.models  # noqa: F401,E402

from app.core.database import async_session_factory
from app.employees.models import Employee
from app.employees.service import _build_employee_profile
from app.memory.service import (
    add_user_to_tenant,
    create_dataset,
    create_employee_user,
    get_or_create_admin,
    grant_tenant_read,
    init_cognee,
    remember,
)
from app.organizations.models import Organization

logger = logging.getLogger(__name__)


async def backfill(dry_run: bool) -> None:
    await init_cognee()

    async with async_session_factory() as db:
        rows = await db.execute(
            select(Employee, Organization)
            .join(Organization, Employee.org_id == Organization.id)
            .where(
                Organization.cognee_tenant_id.is_not(None),
                Employee.cognee_user_id.is_(None),
            )
        )
        broken = rows.all()

        if not broken:
            print("No employees need backfilling. Everyone's memory is provisioned.")
            return

        print(f"Found {len(broken)} employee(s) missing Cognee provisioning:")
        for emp, org in broken:
            print(f"  - {emp.name} ({emp.id}) in org {org.name} ({org.id})")

        if dry_run:
            print("\nDry run — no changes made. Re-run without --dry-run to fix.")
            return

        admin = await get_or_create_admin()

        for emp, org in broken:
            emp_id, emp_name = emp.id, emp.name  # snapshot before any rollback expires emp
            try:
                cognee_user = await create_employee_user(org.cognee_tenant_id, emp.name)
                await add_user_to_tenant(
                    cognee_user["id"], org.cognee_tenant_id, admin["id"]
                )
                dataset = await create_dataset(f"employee-{emp.id}", cognee_user["id"])
                await grant_tenant_read(dataset["id"], org.cognee_tenant_id, cognee_user["id"])

                profile = _build_employee_profile(emp)
                await remember(
                    profile,
                    f"employee-{emp.id}",
                    cognee_user["id"],
                    dataset_id=dataset["id"],
                    background=True,
                )

                emp.cognee_user_id = cognee_user["id"]
                emp.cognee_user_name = cognee_user["email"]
                emp.cognee_dataset_id = dataset["id"]
                emp.cognee_dataset_name = dataset["name"]
                await db.commit()
                print(f"  fixed: {emp_name} ({emp_id})")
            except Exception:
                await db.rollback()
                logger.exception("Backfill failed for employee %s", emp_id)
                print(f"  FAILED: {emp_name} ({emp_id}) — see logs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List affected employees without fixing them"
    )
    args = parser.parse_args()
    asyncio.run(backfill(args.dry_run))


if __name__ == "__main__":
    main()
