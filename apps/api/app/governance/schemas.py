from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalAssignmentInput(BaseModel):
    agent_type: str
    approver_user_id: UUID


class ApprovalAssignmentResponse(ApprovalAssignmentInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime


class ApprovalAssignmentsUpdate(BaseModel):
    assignments: list[ApprovalAssignmentInput] = Field(max_length=5)


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    employee_id: UUID | None
    job_id: UUID | None
    plan_hash: str
    token_id: str | None
    delegation_id: str | None
    mcp: str
    action: str
    redacted_parameters: dict
    requester_email: str | None
    assigned_approver_id: UUID | None
    status: str
    reason: str | None
    decision: str | None
    execution_result: dict | None
    armoriq_url: str | None
    expires_at: datetime
    decided_at: datetime | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRequestResponse]
    total: int


class ApprovalActionResponse(BaseModel):
    status: str
    approval: ApprovalRequestResponse
    authority: str = "armoriq"
    message: str


class ArmorIQMetricsResponse(BaseModel):
    status: str
    total_plans: int
    total_calls: int
    allow_count: int
    hold_count: int
    block_count: int
    executed_count: int
    failed_count: int
    pending_approvals: int
    allow_percent: float
    hold_percent: float
    block_percent: float
    top_agents: list[dict]
    top_mcps: list[dict]
    top_tools: list[dict]
    recent_plans: list[dict]
    registration_healthy: bool
    telemetry_healthy: bool
