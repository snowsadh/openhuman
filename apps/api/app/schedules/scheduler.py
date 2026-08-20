from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.agent.jobs.models import AgentJob
from app.core.config import settings
from app.core.database import async_session_factory
from app.employees.models import Employee
from app.schedules.models import EmployeeSchedule
from app.schedules.service import next_run_at, skipped_occurrence_count

logger = logging.getLogger(__name__)


class EmployeeScheduler:
    def __init__(self) -> None:
        self.running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="employee-scheduler")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self.running:
            try:
                await self.tick()
            except Exception:
                logger.exception("Employee schedule tick failed")
            await asyncio.sleep(settings.schedule_poll_interval_seconds)

    async def tick(self) -> int:
        now = datetime.now(UTC)
        async with async_session_factory() as db:
            due = list((await db.execute(
                select(EmployeeSchedule)
                .join(Employee, Employee.id == EmployeeSchedule.employee_id)
                .where(
                    EmployeeSchedule.status == "active",
                    EmployeeSchedule.next_run_at <= now,
                    Employee.status == "active",
                )
                .order_by(EmployeeSchedule.next_run_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            )).scalars().all())
            for schedule in due:
                occurrence = schedule.next_run_at
                skipped = skipped_occurrence_count(
                    schedule.cron_expression, schedule.timezone, occurrence, now
                )
                db.add(AgentJob(
                    employee_id=schedule.employee_id,
                    schedule_id=schedule.id,
                    scheduled_for=occurrence,
                    available_at=now,
                    platform=schedule.platform,
                    channel_id=schedule.channel_id,
                    thread_key=f"cron:{schedule.id}:{occurrence.isoformat()}",
                    job_type="scheduled_employee_run",
                    payload={
                        "schedule_name": schedule.name,
                        "prompt": schedule.prompt,
                        "timezone": schedule.timezone,
                        "thread_id": schedule.thread_id,
                        "catch_up": occurrence < now,
                        "missed_occurrences_skipped": skipped,
                    },
                    user_text=schedule.prompt,
                    status="pending",
                    delivery_status="pending",
                ))
                # Latest-only catch-up: compute from wall-clock now, not from
                # the old occurrence, so older missed intervals are skipped.
                schedule.next_run_at = next_run_at(
                    schedule.cron_expression, schedule.timezone, base=now
                )
            await db.commit()
            return len(due)
