from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateChannelAssignmentRequest(BaseModel):
    platform: str  # "discord" | "slack"
    channel_id: str
    channel_name: str | None = None


class ChannelAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    channel_id: str
    channel_name: str | None = None
