from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity
from app.auth.models import User
from app.channel_assignments.models import ChannelAssignment
from app.channel_assignments.schemas import (
    ChannelAssignmentResponse,
    CreateChannelAssignmentRequest,
)
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.employees.models import Employee
from app.organizations.models import Organization

router = APIRouter(
    prefix="/api/organizations/{org_id}/employees/{emp_id}/channel-assignments",
    tags=["channel-assignments"],
)

_ALLOWED_PLATFORMS = {"discord", "slack"}


async def _verify_access(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID
) -> Employee:
    """Confirm user owns the org and emp belongs to that org. Returns the employee."""
    org = await db.scalar(
        select(Organization).where(
            Organization.id == org_id, Organization.owner_id == user_id
        )
    )
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    emp = await db.scalar(
        select(Employee).where(Employee.id == emp_id, Employee.org_id == org_id)
    )
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return emp  # type: ignore[return-value]


@router.post("", response_model=ChannelAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_assignment(
    org_id: UUID,
    emp_id: UUID,
    data: CreateChannelAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChannelAssignmentResponse:
    if data.platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"platform must be one of {sorted(_ALLOWED_PLATFORMS)}",
        )
    emp = await _verify_access(db, org_id, emp_id, current_user.id)
    ca = ChannelAssignment(
        employee_id=emp_id,
        platform=data.platform,
        channel_id=data.channel_id,
        channel_name=data.channel_name,
    )
    db.add(ca)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Channel assignment already exists for this employee/platform/channel",
        )
    await db.refresh(ca)

    # Record activity (best-effort)
    try:
        await record_activity(
            db,
            org_id,
            "channel_assigned",
            f"Channel #{data.channel_name} ({data.platform}) assigned to {emp.name}",
            employee_id=emp_id,
            employee_name=emp.name,
            platform=data.platform,
            metadata={
                "channel_id": data.channel_id,
                "channel_name": data.channel_name,
                "platform": data.platform,
            },
        )
    except Exception:
        pass

    return ChannelAssignmentResponse.model_validate(ca, from_attributes=True)


@router.get("", response_model=list[ChannelAssignmentResponse])
async def list_channel_assignments(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChannelAssignmentResponse]:
    await _verify_access(db, org_id, emp_id, current_user.id)
    result = await db.execute(
        select(ChannelAssignment).where(ChannelAssignment.employee_id == emp_id)
    )
    return [
        ChannelAssignmentResponse.model_validate(ca, from_attributes=True)
        for ca in result.scalars().all()
    ]


@router.delete("/{ca_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_assignment(
    org_id: UUID,
    emp_id: UUID,
    ca_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    emp = await _verify_access(db, org_id, emp_id, current_user.id)
    ca = await db.scalar(
        select(ChannelAssignment).where(
            ChannelAssignment.id == ca_id,
            ChannelAssignment.employee_id == emp_id,
        )
    )
    if ca is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel assignment not found"
        )

    # Record activity BEFORE delete (best-effort)
    try:
        await record_activity(
            db,
            org_id,
            "channel_unassigned",
            f"Channel #{ca.channel_name} ({ca.platform}) unassigned from {emp.name}",
            employee_id=emp_id,
            employee_name=emp.name,
            platform=ca.platform,
            metadata={
                "channel_id": ca.channel_id,
                "channel_name": ca.channel_name,
                "platform": ca.platform,
            },
        )
    except Exception:
        pass

    await db.delete(ca)
    await db.commit()
