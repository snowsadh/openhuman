from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.guardrails.input import check_input
from app.agent.jobs.models import AgentJob
from app.channel_assignments.models import ChannelAssignment
from app.employees.models import Employee
from app.organizations.models import Organization
from app.schedules.models import EmployeeSchedule
from app.schedules.schemas import ScheduleCreate, ScheduleUpdate


class ScheduleValidationError(ValueError):
    pass


def next_run_at(expression: str, timezone_name: str, *, base: datetime | None = None) -> datetime:
    if len(expression.split()) != 5 or not croniter.is_valid(expression):
        raise ScheduleValidationError("cron_expression must be a valid five-field cron expression")
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleValidationError(f"Unknown IANA timezone: {timezone_name}") from exc
    base_utc = base or datetime.now(UTC)
    local_base = base_utc.astimezone(tz)
    return croniter(expression, local_base).get_next(datetime).astimezone(UTC)


def skipped_occurrence_count(
    expression: str, timezone_name: str, occurrence: datetime, now: datetime
) -> int:
    """Count older missed fires skipped by latest-only catch-up, with a safety cap."""
    tz = ZoneInfo(timezone_name)
    iterator = croniter(expression, occurrence.astimezone(tz))
    skipped = 0
    for _ in range(10_000):
        candidate = iterator.get_next(datetime).astimezone(UTC)
        if candidate > now:
            break
        skipped += 1
    return skipped


def validate_prompt(prompt: str) -> None:
    blocked, reason = check_input(prompt, {"threat_scan_scope": "strict"})
    if blocked:
        raise ScheduleValidationError(f"Scheduled prompt rejected: {reason}")


async def verify_employee_access(
    db: AsyncSession, org_id: UUID, employee_id: UUID, user_id: UUID
) -> Employee | None:
    owned = await db.scalar(
        select(Organization.id).where(Organization.id == org_id, Organization.owner_id == user_id)
    )
    if owned is None:
        return None
    return await db.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.org_id == org_id)
    )


async def validate_destination(
    db: AsyncSession, employee_id: UUID, platform: str, channel_id: str
) -> None:
    assignment = await db.scalar(
        select(ChannelAssignment.id).where(
            ChannelAssignment.employee_id == employee_id,
            ChannelAssignment.platform == platform,
            ChannelAssignment.channel_id == channel_id,
        )
    )
    if assignment is None:
        raise ScheduleValidationError("Destination must be assigned to this employee")


async def create_schedule(
    db: AsyncSession, org_id: UUID, employee: Employee, data: ScheduleCreate
) -> EmployeeSchedule:
    validate_prompt(data.prompt)
    await validate_destination(db, employee.id, data.platform, data.channel_id)
    schedule = EmployeeSchedule(
        org_id=org_id,
        employee_id=employee.id,
        name=data.name.strip(),
        prompt=data.prompt.strip(),
        cron_expression=data.cron_expression.strip(),
        timezone=data.timezone,
        platform=data.platform,
        channel_id=data.channel_id,
        thread_id=data.thread_id or None,
        next_run_at=next_run_at(data.cron_expression, data.timezone),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def update_schedule(
    db: AsyncSession, schedule: EmployeeSchedule, data: ScheduleUpdate
) -> EmployeeSchedule:
    values = data.model_dump(exclude_unset=True)
    if "prompt" in values:
        validate_prompt(values["prompt"])
        values["prompt"] = values["prompt"].strip()
    platform = values.get("platform", schedule.platform)
    channel_id = values.get("channel_id", schedule.channel_id)
    if "platform" in values or "channel_id" in values:
        await validate_destination(db, schedule.employee_id, platform, channel_id)
    for key, value in values.items():
        setattr(schedule, key, value)
    if {"cron_expression", "timezone", "status"} & values.keys() and schedule.status == "active":
        schedule.next_run_at = next_run_at(schedule.cron_expression, schedule.timezone)
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def enqueue_schedule_run(
    db: AsyncSession,
    schedule: EmployeeSchedule,
    *,
    scheduled_for: datetime | None = None,
) -> AgentJob:
    occurrence = scheduled_for or datetime.now(UTC)
    job = AgentJob(
        employee_id=schedule.employee_id,
        schedule_id=schedule.id,
        scheduled_for=occurrence,
        available_at=datetime.now(UTC),
        platform=schedule.platform,
        channel_id=schedule.channel_id,
        thread_key=f"cron:{schedule.id}:{occurrence.isoformat()}",
        job_type="scheduled_employee_run",
        payload={
            "schedule_name": schedule.name,
            "prompt": schedule.prompt,
            "timezone": schedule.timezone,
            "thread_id": schedule.thread_id,
        },
        user_text=schedule.prompt,
        status="pending",
        delivery_status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job
