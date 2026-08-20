from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActivityEventResponse(BaseModel):
    """A single unified activity event from any source table."""

    model_config = ConfigDict(from_attributes=True)

    id: str  # composite: "{source}:{uuid}" or "{source}:{uuid}:{epoch}"
    event_type: str  # agent_run | document_upload | employee_created | employee_updated | tool_usage | human_escalation | memory_operation
    summary: str  # human-readable one-liner
    description: str | None = None  # longer detail (JSON string for expandable section)
    employee_id: UUID | None = None
    employee_name: str | None = None
    platform: str | None = None  # slack | discord | api
    status: str | None = None  # job status or document status
    metadata: dict | None = None  # extra structured payload
    occurred_at: datetime


class ActivityFeedResponse(BaseModel):
    """Paginated activity feed."""

    events: list[ActivityEventResponse]
    total: int  # total count matching filters
    next_offset: int | None = None  # None if no more pages


class ActivityStatsResponse(BaseModel):
    """Today's activity counts grouped by type."""

    total_today: int
    agent_runs: int
    document_uploads: int
    employee_events: int
    tool_usages: int
    human_escalations: int
    memory_operations: int
