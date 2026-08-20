from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.agent.build import build_graph
from app.agent.jobs.models import AgentJob
from app.agent.router import get_graph_for_employee
from app.core.config import settings
from app.core.database import async_session_factory
from app.employees.models import Employee
from app.schedules.delivery import deliver_result, is_silent_response
from app.schedules.models import EmployeeSchedule
from app.schedules.service import ScheduleValidationError, validate_destination

logger = logging.getLogger(__name__)

_AUTONOMOUS_DENY_TOOLS = {
    "cronjob",
    "delegate_task",
    "escalate_to_human",
    "escalate_to_human_interactive",
}


async def run_scheduled_employee_job(job: AgentJob) -> None:
    if job.schedule_id is None:
        job.status = "failed"
        job.error = "Scheduled run has no schedule_id"
        return

    async with async_session_factory() as db:
        schedule = await db.scalar(
            select(EmployeeSchedule).where(EmployeeSchedule.id == job.schedule_id)
        )
        employee = await db.scalar(select(Employee).where(Employee.id == job.employee_id))
        if schedule is None or employee is None:
            job.status = "failed"
            job.error = "Schedule or employee no longer exists"
            return
        if employee.status != "active":
            job.status = "cancelled"
            job.error = f"Employee is {employee.status}"
            job.delivery_status = "skipped"
            return
        try:
            await validate_destination(db, employee.id, schedule.platform, schedule.channel_id)
        except ScheduleValidationError as exc:
            job.status = "failed"
            job.error = str(exc)
            job.delivery_status = "failed"
            schedule.last_run_at = datetime.now(UTC)
            schedule.last_run_status = "delivery_failed"
            schedule.last_error = str(exc)
            await db.commit()
            return

        result_state: dict | None = None
        last_error: Exception | None = None
        for attempt in range(1, settings.schedule_max_attempts + 1):
            job.attempt = attempt
            try:
                _cached_graph, all_tools = await get_graph_for_employee(db, employee.id)
                autonomous_tools = [t for t in all_tools if t.name not in _AUTONOMOUS_DENY_TOOLS]
                graph = build_graph(autonomous_tools)
                result_state = await asyncio.wait_for(
                    graph.ainvoke(
                        {
                            "messages": [HumanMessage(content=schedule.prompt)],
                            "platform": schedule.platform,
                            "employee_id": str(employee.id),
                            "tool_round": 0,
                        },
                        config={"configurable": {
                            "db": db,
                            "employee_id": str(employee.id),
                            "all_tools": autonomous_tools,
                            "thread_id": f"cron:{schedule.id}:{job.id}",
                            "platform": schedule.platform,
                            "channel_id": schedule.channel_id,
                            "thread_ts": schedule.thread_id,
                            "scheduled_run": True,
                        }},
                    ),
                    timeout=settings.schedule_run_timeout_seconds,
                )
                if result_state.get("error"):
                    raise RuntimeError(str(result_state["error"]))
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                logger.exception("Scheduled run %s attempt %d failed", job.id, attempt)
                if attempt < settings.schedule_max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))

        if last_error is not None or result_state is None:
            job.status = "failed"
            job.error = str(last_error or "Scheduled agent returned no result")[:2000]
            schedule.last_run_at = datetime.now(UTC)
            schedule.last_run_status = "failed"
            schedule.last_error = job.error
            await db.commit()
            return

        response = str(result_state.get("response") or "").strip()
        job.result_text = response[:10000]
        files = list(result_state.get("files") or [])
        if is_silent_response(response):
            job.delivery_status = "suppressed"
        else:
            delivery_error: Exception | None = None
            for attempt in range(1, settings.schedule_delivery_attempts + 1):
                try:
                    await deliver_result(
                        employee,
                        platform=schedule.platform,
                        channel_id=schedule.channel_id,
                        thread_id=schedule.thread_id,
                        text=response,
                        files=files,
                        idempotency_key=str(job.id),
                    )
                    delivery_error = None
                    job.delivery_status = "delivered"
                    break
                except Exception as exc:
                    delivery_error = exc
                    if attempt < settings.schedule_delivery_attempts:
                        await asyncio.sleep(2 ** (attempt - 1))
            if delivery_error is not None:
                job.status = "failed"
                job.delivery_status = "failed"
                job.delivery_error = str(delivery_error)[:2000]
                job.error = "Agent completed but result delivery failed"
                schedule.last_run_at = datetime.now(UTC)
                schedule.last_run_status = "delivery_failed"
                schedule.last_error = job.delivery_error
                await db.commit()
                return

        job.status = "succeeded"
        schedule.last_run_at = datetime.now(UTC)
        schedule.last_run_status = "succeeded"
        schedule.last_error = None
        await db.commit()
