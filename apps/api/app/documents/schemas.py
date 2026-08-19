from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    employee_id: UUID | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str
    storage_backend: str = "local"
    uploaded_at: datetime
    employee_name: str | None = None


class DocumentsStatsResponse(BaseModel):
    total_files: int
    total_size_bytes: int
    org_files_count: int
    org_size_bytes: int
    agent_files_count: int
    agent_size_bytes: int
    agents_with_files_count: int
