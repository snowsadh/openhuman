from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateOrganizationRequest(BaseModel):
    name: str
    description: str | None = None
    what_it_does: str | None = None
    website_url: str | None = None


class UpdateOrganizationRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    what_it_does: str | None = None
    website_url: str | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    what_it_does: str | None = None
    website_url: str | None = None
    owner_id: UUID
    cognee_tenant_id: str | None = None
    cognee_dataset_name: str | None = None
    created_at: datetime
