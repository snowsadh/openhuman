from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.governance.models import ApprovalAssignment, ApprovalRequest
from app.governance.schemas import (
    ApprovalActionResponse,
    ApprovalAssignmentResponse,
    ApprovalAssignmentsUpdate,
    ApprovalListResponse,
    ApprovalRequestResponse,
    ArmorIQMetricsResponse,
)
from app.governance.service import build_armoriq_metrics, expire_pending_approvals
from app.organizations.models import Organization

approval_router = APIRouter(prefix="/api/approvals", tags=["approvals"])
assignment_router = APIRouter(prefix="/api/organizations", tags=["approvals"])
metrics_router = APIRouter(prefix="/api/agent/armoriq", tags=["agent"])


async def _require_owner(db: AsyncSession, org_id: UUID, user: User) -> Organization:
    organization = await db.scalar(
        select(Organization).where(
            Organization.id == org_id,
            Organization.owner_id == user.id,
        )
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


async def _authorized_approval(
    db: AsyncSession,
    approval_id: UUID,
    user: User,
) -> ApprovalRequest:
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    organization = await db.get(Organization, approval.org_id)
    if organization is None or (
        organization.owner_id != user.id and approval.assigned_approver_id != user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    if approval.status == "pending" and approval.expires_at <= datetime.now(UTC):
        approval.status = "expired"
        approval.decision = "expired"
        approval.decided_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(approval)
    return approval


@approval_router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    organization_id: UUID = Query(...),
    approval_status: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalListResponse:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if organization.owner_id != current_user.id:
        assigned = await db.scalar(
            select(ApprovalAssignment.id).where(
                ApprovalAssignment.org_id == organization_id,
                ApprovalAssignment.approver_user_id == current_user.id,
            )
        )
        if assigned is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
    await expire_pending_approvals(db, organization_id)
    filters = [ApprovalRequest.org_id == organization_id]
    if organization.owner_id != current_user.id:
        filters.append(ApprovalRequest.assigned_approver_id == current_user.id)
    if approval_status:
        filters.append(ApprovalRequest.status == approval_status)
    total = await db.scalar(select(func.count(ApprovalRequest.id)).where(*filters))
    rows = list(
        (
            await db.scalars(
                select(ApprovalRequest)
                .where(*filters)
                .order_by(ApprovalRequest.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return ApprovalListResponse(items=rows, total=int(total or 0))


@approval_router.get("/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    approval_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequest:
    return await _authorized_approval(db, approval_id, current_user)


async def _armor_authority_response(
    approval_id: UUID,
    action: str,
    db: AsyncSession,
    current_user: User,
) -> ApprovalActionResponse:
    approval = await _authorized_approval(db, approval_id, current_user)
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval is already {approval.status}",
        )
    return ApprovalActionResponse(
        status="open_armoriq",
        approval=approval,
        message=(
            f"{action.title()} this delegation in ArmorIQ. OpenHuman will poll the "
            "same record and will not override ArmorIQ locally."
        ),
    )


@approval_router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve_request(
    approval_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalActionResponse:
    return await _armor_authority_response(approval_id, "approve", db, current_user)


@approval_router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject_request(
    approval_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalActionResponse:
    return await _armor_authority_response(approval_id, "reject", db, current_user)


@assignment_router.get(
    "/{org_id}/approval-assignments",
    response_model=list[ApprovalAssignmentResponse],
)
async def list_approval_assignments(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApprovalAssignment]:
    await _require_owner(db, org_id, current_user)
    return list(
        (
            await db.scalars(
                select(ApprovalAssignment)
                .where(ApprovalAssignment.org_id == org_id)
                .order_by(ApprovalAssignment.agent_type)
            )
        ).all()
    )


@assignment_router.put(
    "/{org_id}/approval-assignments",
    response_model=list[ApprovalAssignmentResponse],
)
async def replace_approval_assignments(
    org_id: UUID,
    payload: ApprovalAssignmentsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApprovalAssignment]:
    organization = await _require_owner(db, org_id, current_user)
    # The current product has owner-only organizations. Keep assignments inside
    # that identity boundary until organization memberships are introduced.
    if any(item.approver_user_id != organization.owner_id for item in payload.assignments):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Approver must currently be the organization owner",
        )
    existing = list(
        (
            await db.scalars(
                select(ApprovalAssignment).where(ApprovalAssignment.org_id == org_id)
            )
        ).all()
    )
    for row in existing:
        await db.delete(row)
    await db.flush()
    rows = [
        ApprovalAssignment(
            org_id=org_id,
            agent_type=item.agent_type,
            approver_user_id=item.approver_user_id,
        )
        for item in payload.assignments
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


@metrics_router.get("/metrics", response_model=ArmorIQMetricsResponse)
async def armoriq_metrics(
    organization_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ArmorIQMetricsResponse:
    await _require_owner(db, organization_id, current_user)
    await expire_pending_approvals(db, organization_id)
    return ArmorIQMetricsResponse(**(await build_armoriq_metrics(db, organization_id)))
