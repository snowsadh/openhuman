from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """An attribution citation for information returned by the agent."""

    source: str
    content: str
    confidence: float | None = None


class FileAttachment(BaseModel):
    """A file the agent wants to attach to its response (e.g. chart PNG, PDF).

    ``data`` is base64-encoded so the value is JSON-serializable through
    the graph state without a separate blob-storage round-trip.
    """

    filename: str
    content_type: str = Field(description="MIME type such as ``image/png`` or ``application/pdf``")
    data: str = Field(description="Base64-encoded file content")
    title: str = Field(description="Human-readable label shown in Slack")


class MessageInput(BaseModel):
    """Payload representing an incoming message from any gateway or tester."""

    content: str
    platform: str  # "discord" | "slack" | "api"
    channel_id: str
    user_id: str
    employee_id: UUID
    employee_name: str | None = None
    org_name: str | None = None
    system_prompt_template: str | None = None


class AgentResponse(BaseModel):
    """Payload returned by the agent after compiling a response."""

    response: str | None
    files: list[FileAttachment] = Field(default_factory=list)
    tool_calls_count: int
    error: str | None = None
