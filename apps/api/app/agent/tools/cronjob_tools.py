"""Agent-facing schedule management backed by durable schedule definitions."""
from __future__ import annotations

import json
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.employees.models import Employee
from app.schedules.models import EmployeeSchedule
from app.schedules.schemas import ScheduleCreate, ScheduleUpdate
from app.schedules.service import (
    ScheduleValidationError,
    create_schedule,
    enqueue_schedule_run,
    update_schedule,
)


def _result(success: bool, data=None, error: str | None = None) -> str:
    return json.dumps({"success": success, "data": data, "error": error}, default=str)


@tool
async def cronjob(
    action: str,
    job_id: str | None = None,
    prompt: str | None = None,
    schedule: str | None = None,
    name: str | None = None,
    timezone: str | None = None,
    platform: str | None = None,
    channel_id: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Create, list, update, pause, resume, remove, or run recurring employee work.

    Schedules use five-field cron expressions and IANA timezone names. Results
    are delivered to an assigned Slack or Discord channel.
    """
    ctx = (config or {}).get("configurable", {})
    db: AsyncSession | None = ctx.get("db")
    employee_id = ctx.get("employee_id")
    if db is None or not employee_id:
        return _result(False, error="Schedule management requires employee and database context")
    try:
        employee_uuid = UUID(str(employee_id))
        employee = await db.scalar(select(Employee).where(Employee.id == employee_uuid))
        if employee is None:
            return _result(False, error="Employee not found")
        normalized = action.strip().lower()
        target_platform = platform or ctx.get("platform")
        target_channel = channel_id or ctx.get("channel_id")

        if normalized == "create":
            if not prompt or not schedule or not target_platform or not target_channel:
                return _result(False, error="prompt, schedule, platform, and assigned channel are required")
            created = await create_schedule(db, employee.org_id, employee, ScheduleCreate(
                name=name or "Scheduled duty",
                prompt=prompt,
                cron_expression=schedule,
                timezone=timezone or "UTC",
                platform=target_platform,
                channel_id=target_channel,
                thread_id=ctx.get("thread_ts"),
            ))
            return _result(True, {"job_id": str(created.id), "status": created.status, "next_run_at": created.next_run_at})

        if normalized == "list":
            rows = list((await db.execute(select(EmployeeSchedule).where(
                EmployeeSchedule.employee_id == employee_uuid
            ).order_by(EmployeeSchedule.created_at.desc()))).scalars().all())
            return _result(True, {"jobs": [{
                "job_id": str(row.id), "name": row.name, "schedule": row.cron_expression,
                "timezone": row.timezone, "status": row.status, "next_run_at": row.next_run_at,
                "last_run_status": row.last_run_status,
            } for row in rows]})

        if normalized not in {"update", "pause", "resume", "remove", "run"} or not job_id:
            return _result(False, error="Valid actions: create, list, update, pause, resume, remove, run")
        row = await db.scalar(select(EmployeeSchedule).where(
            EmployeeSchedule.id == UUID(job_id), EmployeeSchedule.employee_id == employee_uuid
        ))
        if row is None:
            return _result(False, error="Schedule not found")
        if normalized == "remove":
            await db.delete(row)
            await db.commit()
            return _result(True, {"job_id": job_id, "status": "removed"})
        if normalized == "run":
            if employee.status != "active":
                return _result(False, error="Employee must be active")
            run = await enqueue_schedule_run(db, row)
            return _result(True, {"job_id": job_id, "run_id": str(run.id), "status": run.status})
        changes: dict = {}
        if normalized == "pause":
            changes["status"] = "paused"
        elif normalized == "resume":
            changes["status"] = "active"
        else:
            if prompt is not None:
                changes["prompt"] = prompt
            if schedule is not None:
                changes["cron_expression"] = schedule
            if name is not None:
                changes["name"] = name
            if timezone is not None:
                changes["timezone"] = timezone
            if platform is not None:
                changes["platform"] = platform
            if channel_id is not None:
                changes["channel_id"] = channel_id
        updated = await update_schedule(db, row, ScheduleUpdate(**changes))
        return _result(True, {"job_id": job_id, "status": updated.status, "next_run_at": updated.next_run_at})
    except (ValueError, ScheduleValidationError) as exc:
        return _result(False, error=str(exc))
