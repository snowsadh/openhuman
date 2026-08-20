from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.schemas import ActivityFeedResponse, ActivityStatsResponse
from app.activity.service import get_activity_feed, get_activity_stats
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=ActivityFeedResponse)
async def list_activity(
    organization_id: UUID = Query(..., description="Organization ID"),
    event_types: list[str] | None = Query(
        None,
        description="Filter by event types (ai_engine, agent_run, document_upload, employee_created, employee_updated, tool_usage, human_escalation, memory_operation)",
    ),
    employee_id: UUID | None = Query(None, description="Filter by employee"),
    employee_type: str | None = Query(None, description="Filter by bot type"),
    q: str | None = Query(None, description="Full-text search across summary/description"),
    date_from: datetime | None = Query(None, description="Start date (ISO 8601)"),
    date_to: datetime | None = Query(None, description="End date (ISO 8601)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size (max 100)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityFeedResponse:
    """Get a unified activity feed for the organization.

    Returns events from agent runs, document uploads, and employee lifecycle
    changes in a single chronological stream.
    """
    return await get_activity_feed(
        db,
        organization_id,
        event_types=event_types,
        employee_id=employee_id,
        employee_type=employee_type,
        q=q,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )


@router.get("/stats", response_model=ActivityStatsResponse)
async def get_activity_stats_route(
    organization_id: UUID = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityStatsResponse:
    """Get today's activity statistics grouped by event type."""
    return await get_activity_stats(db, organization_id)
