from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=4000)
    cron_expression: str = Field(min_length=9, max_length=100)
    timezone: str = Field(default="UTC", max_length=100)
    platform: str = Field(pattern=r"^(slack|discord)$")
    channel_id: str = Field(min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    cron_expression: str | None = Field(default=None, min_length=9, max_length=100)
    timezone: str | None = Field(default=None, max_length=100)
    platform: str | None = Field(default=None, pattern=r"^(slack|discord)$")
    channel_id: str | None = Field(default=None, min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, pattern=r"^(active|paused)$")


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    employee_id: UUID
    name: str
    prompt: str
    cron_expression: str
    timezone: str
    platform: str
    channel_id: str
    thread_id: str | None
    status: str
    next_run_at: datetime
    last_run_at: datetime | None
    last_run_status: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime | None


class ScheduleRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID | None
    status: str
    scheduled_for: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    result_text: str | None
    error: str | None
    attempt: int
    delivery_status: str | None
    delivery_error: str | None
