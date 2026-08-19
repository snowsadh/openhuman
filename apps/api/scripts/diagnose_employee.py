#!/usr/bin/env python3
"""
Read-only diagnostic: dump an employee's escalation/Notion provisioning state.

Usage:
    python -m scripts.diagnose_employee --name Alison
    python -m scripts.diagnose_employee --employee-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

import app.auth.models  # noqa: F401,E402
import app.channel_assignments.models  # noqa: F401,E402
import app.documents.models  # noqa: F401,E402
import app.organizations.models  # noqa: F401,E402

from app.agent.tools.mcp.models import McpConnection
from app.core.database import async_session_factory
from app.employees.models import Employee
from app.organizations.models import Organization


async def diagnose(name: str | None, employee_id: str | None) -> None:
    async with async_session_factory() as db:
        stmt = select(Employee, Organization).join(
            Organization, Employee.org_id == Organization.id
        )
        if employee_id:
            stmt = stmt.where(Employee.id == employee_id)
        elif name:
            stmt = stmt.where(Employee.name.ilike(f"%{name}%"))
        rows = (await db.execute(stmt)).all()

        if not rows:
            print("No matching employees found.")
            return

        for emp, org in rows:
            print("=" * 70)
            print(f"Employee: {emp.name} ({emp.id})")
            print(f"  employee_type:      {emp.employee_type}")
            print(f"  org:                 {org.name} ({org.id})")
            print(f"  escalation_policy:   {emp.escalation_policy!r}")
            print(f"  slack_token set:     {bool(emp.slack_token_enc)}")
            print(f"  cognee_user_id:      {emp.cognee_user_id!r}")
            print(f"  duties:              {emp.duties!r}")

            conns = (
                await db.execute(
                    select(McpConnection).where(
                        McpConnection.org_id == org.id,
                        (McpConnection.employee_id == emp.id)
                        | (McpConnection.employee_id.is_(None)),
                    )
                )
            ).scalars().all()
            if not conns:
                print("  mcp_connections:     (none)")
            else:
                print("  mcp_connections:")
                for c in conns:
                    scope = "org-wide" if c.employee_id is None else "employee"
                    print(
                        f"    - {c.connector_slug} [{scope}] status={c.status} "
                        f"auth_type={c.auth_type} id={c.id}"
                    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", help="Case-insensitive substring match on employee name")
    parser.add_argument("--employee-id", help="Exact employee UUID")
    args = parser.parse_args()
    if not args.name and not args.employee_id:
        parser.error("Provide --name or --employee-id")
    asyncio.run(diagnose(args.name, args.employee_id))


if __name__ == "__main__":
    main()
