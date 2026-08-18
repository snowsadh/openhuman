from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.channel_assignments.schemas import ChannelAssignmentResponse

_VALID_EMPLOYEE_TYPES_PATTERN = r"^(legal-compliance|support|hr|general|sales)$"


class CreateEmployeeRequest(BaseModel):
    name: str
    employee_type: str = Field(
        ...,
        pattern=_VALID_EMPLOYEE_TYPES_PATTERN,
        description="One of: legal-compliance, support, hr, general, sales",
    )
    role: str | None = None
    personality: dict | None = None
    specialization: str | None = None
    duties: list | None = None
    memory_policy: dict | None = None
    escalation_policy: dict | None = None


class UpdateEmployeeRequest(BaseModel):
    name: str | None = None
    employee_type: str | None = Field(
        None,
        pattern=_VALID_EMPLOYEE_TYPES_PATTERN,
        description="One of: legal-compliance, support, hr, general, sales",
    )
    role: str | None = None
    personality: dict | None = None
    specialization: str | None = None
    duties: list | None = None
    memory_policy: dict | None = None
    escalation_policy: dict | None = None
    status: str | None = None


class DiscordTokenRequest(BaseModel):
    token: str


class SlackTokenRequest(BaseModel):
    token: str


class StatusRequest(BaseModel):
    status: str  # "active" | "inactive"




class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: UUID
    org_id: UUID
    name: str
    employee_type: str | None = None
    role: str | None = None
    personality: dict | None = None
    specialization: str | None = None
    duties: list | None = None
    memory_policy: dict | None = None
    escalation_policy: dict | None = None
    mcp_connections: list | None = None
    status: str
    has_discord_token: bool
    has_slack_token: bool

    slack_team_name: str | None = None
    slack_bot_user_id: str | None = None
    cognee_user_id: str | None = None
    cognee_dataset_name: str | None = None
    channel_assignments: list[ChannelAssignmentResponse] = []
    created_at: datetime
    updated_at: datetime | None = None
    operational_status: str = "offline"
    current_task: str | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
