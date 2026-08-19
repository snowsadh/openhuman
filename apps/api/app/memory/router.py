from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.employees.models import Employee
from app.memory.schemas import (
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemoryResultSchema,
    MemorySearchRequest,
    MemorySearchResponse,
)
from app.memory.service import recall, remember
from app.organizations.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


async def _verify_employee_ownership(
    db: AsyncSession, employee_id: UUID, user_id: UUID
) -> Employee:
    """Return Employee if it belongs to an org owned by user_id, else 404."""
    emp = await db.scalar(
        select(Employee)
        .join(Organization, Employee.org_id == Organization.id)
        .where(Employee.id == employee_id, Organization.owner_id == user_id)
    )
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    return emp


@router.post("/search", response_model=MemorySearchResponse)
async def search(
    data: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemorySearchResponse:
    """Search employee personal memory and shared org knowledge."""
    emp = await _verify_employee_ownership(db, data.employee_id, current_user.id)

    org = await db.scalar(
        select(Organization).where(Organization.id == emp.org_id)
    )

    # Build dataset list: employee dataset + org dataset
    datasets: list[str] = []
    if emp.cognee_dataset_name:
        datasets.append(emp.cognee_dataset_name)
    if org and org.cognee_dataset_name:
        datasets.append(org.cognee_dataset_name)

    # Determine which Cognee user to search as
    user_id = emp.cognee_user_id or (
        org.cognee_system_user_id if org else None
    )
    if not user_id or not datasets:
        return MemorySearchResponse(results=[], query=data.query)

    try:
        results = await recall(data.query, user_id, datasets=datasets)
    except Exception:
        logger.exception(
            "Cognee recall failed for employee %s", data.employee_id
        )
        results = []

    # Record activity (best-effort)
    try:
        await record_activity(
            db,
            emp.org_id,
            "memory_operation",
            f"Memory search: '{data.query[:100]}'",
            employee_id=data.employee_id,
            employee_name=emp.name,
            platform="api",
            metadata={
                "operation": "search",
                "query": data.query,
                "results_count": len(results),
            },
        )
    except Exception:
        pass

    schemas = [
        MemoryResultSchema(
            text=r.get("text", ""),
            dataset_name=r.get("dataset_name", ""),
            source=r.get("source", "graph"),
            score=r.get("score"),
        )
        for r in results
    ]
    return MemorySearchResponse(results=schemas, query=data.query)


@router.post("/ingest", response_model=MemoryIngestResponse)
async def ingest(
    data: MemoryIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryIngestResponse:
    """Ingest a fact into the employee's personal memory."""
    emp = await _verify_employee_ownership(db, data.employee_id, current_user.id)

    if not emp.cognee_user_id or not emp.cognee_dataset_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee Cognee not provisioned yet",
        )

    ingest_ok = True
    try:
        await remember(
            data.content,
            emp.cognee_dataset_name,
            emp.cognee_user_id,
            dataset_id=emp.cognee_dataset_id,
            background=True,
        )
    except Exception:
        logger.exception(
            "Cognee remember failed for employee %s", data.employee_id
        )
        ingest_ok = False

    # Record activity (best-effort)
    try:
        content_preview = data.content[:100] if data.content else "(empty)"
        await record_activity(
            db,
            emp.org_id,
            "memory_operation",
            f"Memory ingest: {content_preview}",
            employee_id=data.employee_id,
            employee_name=emp.name,
            platform="api",
            status="succeeded" if ingest_ok else "failed",
            metadata={
                "operation": "ingest",
                "content_length": len(data.content) if data.content else 0,
            },
        )
    except Exception:
        pass

    if not ingest_ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest memory content",
        )

    return MemoryIngestResponse(status="success")
