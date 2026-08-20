from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.jobs.models import AgentJob
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schedules.models import EmployeeSchedule
from app.schedules.schemas import (
    ScheduleCreate,
    ScheduleResponse,
    ScheduleRunResponse,
    ScheduleUpdate,
)
from app.schedules.service import (
    ScheduleValidationError,
    create_schedule,
    enqueue_schedule_run,
    update_schedule,
    verify_employee_access,
)

router = APIRouter(
    prefix="/api/organizations/{org_id}/employees/{emp_id}/schedules",
    tags=["schedules"],
)


async def _employee(db: AsyncSession, org_id: UUID, emp_id: UUID, user: User):
    employee = await verify_employee_access(db, org_id, emp_id, user.id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


async def _schedule(
    db: AsyncSession, org_id: UUID, emp_id: UUID, schedule_id: UUID
) -> EmployeeSchedule:
    schedule = await db.scalar(select(EmployeeSchedule).where(
        EmployeeSchedule.id == schedule_id,
        EmployeeSchedule.org_id == org_id,
        EmployeeSchedule.employee_id == emp_id,
    ))
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule_route(
    org_id: UUID,
    emp_id: UUID,
    data: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeSchedule:
    employee = await _employee(db, org_id, emp_id, user)
    try:
        return await create_schedule(db, org_id, employee, data)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules_route(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EmployeeSchedule]:
    await _employee(db, org_id, emp_id, user)
    result = await db.execute(select(EmployeeSchedule).where(
        EmployeeSchedule.org_id == org_id,
        EmployeeSchedule.employee_id == emp_id,
    ).order_by(EmployeeSchedule.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule_route(
    org_id: UUID,
    emp_id: UUID,
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeSchedule:
    await _employee(db, org_id, emp_id, user)
    return await _schedule(db, org_id, emp_id, schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule_route(
    org_id: UUID,
    emp_id: UUID,
    schedule_id: UUID,
    data: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmployeeSchedule:
    await _employee(db, org_id, emp_id, user)
    schedule = await _schedule(db, org_id, emp_id, schedule_id)
    try:
        return await update_schedule(db, schedule, data)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule_route(
    org_id: UUID,
    emp_id: UUID,
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    await _employee(db, org_id, emp_id, user)
    schedule = await _schedule(db, org_id, emp_id, schedule_id)
    await db.delete(schedule)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{schedule_id}/run", response_model=ScheduleRunResponse, status_code=202)
async def run_schedule_route(
    org_id: UUID,
    emp_id: UUID,
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentJob:
    employee = await _employee(db, org_id, emp_id, user)
    if employee.status != "active":
        raise HTTPException(status_code=409, detail="Employee must be active to run a schedule")
    schedule = await _schedule(db, org_id, emp_id, schedule_id)
    return await enqueue_schedule_run(db, schedule)


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRunResponse])
async def list_schedule_runs_route(
    org_id: UUID,
    emp_id: UUID,
    schedule_id: UUID,
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AgentJob]:
    await _employee(db, org_id, emp_id, user)
    await _schedule(db, org_id, emp_id, schedule_id)
    result = await db.execute(select(AgentJob).where(
        AgentJob.schedule_id == schedule_id,
        AgentJob.employee_id == emp_id,
    ).order_by(AgentJob.created_at.desc()).limit(min(max(limit, 1), 100)))
    return list(result.scalars().all())
