"""Pydantic schemas for the MCP management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectorStatus(BaseModel):
    """A registry connector with its connection state for an org/employee."""

    slug: str
    name: str
    description: str
    auth_type: str
    auth_types: list[str] = []
    docs_url: str = ""
    requires_custom_server_url: bool = False
    is_connected: bool = False
    connection_count: int = 0
    verified_connection_count: int = 0
    verification_status: str = "unverified"


class McpConnectionRead(BaseModel):
    """Public representation of a stored MCP connection."""

    id: UUID
    connector_slug: str
    auth_type: str
    scopes: list | None = None
    status: str
    verification_status: str = "unverified"
    discovered_tools: list | None = None
    discovered_tool_count: int = 0
    verification_error: str | None = None
    last_verified_at: datetime | None = None
    oauth_expires_at: datetime | None = None
    is_org_wide: bool = False
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class McpConnectionCreate(BaseModel):
    """Payload for creating/updating an API-key or PAT MCP connection."""

    credential: str = Field(..., description="The API key, PAT, or access token to store")
    auth_type: str | None = Field(
        default=None,
        description="Optional auth mode to use for this pasted credential (for example pat_bearer)",
    )
    server_url: str | None = Field(
        default=None,
        description=(
            "Optional per-connection MCP server URL for connectors that require "
            "an org-specific endpoint"
        ),
    )
    scopes: list[str] | None = None
    account_identifier: str | None = Field(
        default=None,
        description="Provider account identity, such as the Zendesk admin email",
    )
    org_wide: bool = Field(
        default=False, description="If True, connection is available to all employees in the org"
    )


class McpConnectionList(BaseModel):
    """Wrapper for listing connections."""

    connections: list[McpConnectionRead]


# ── Catalog schemas ──────────────────────────────────────────────────────────


class CatalogEntryRead(BaseModel):
    """A marketplace catalog entry (read-only)."""

    slug: str
    name: str
    description: str
    category: str
    auth_type: str
    docs_url: str = ""
    is_hardcoded: bool = False
    is_installed: bool = False
    catalog_state: str = "setup_required"
    is_installable: bool = True
    verification_status: str = "unverified"


class McpVerificationRequest(BaseModel):
    """Verify discovery and optionally run one real read tool through ArmorIQ."""

    probe_tool: str | None = Field(
        default=None,
        description="Exact discovered tool name to invoke after tools/list succeeds",
    )
    probe_parameters: dict = Field(default_factory=dict)


class McpVerificationResponse(BaseModel):
    connection: McpConnectionRead
    discovered_tools: list[str]
    probe_executed: bool = False
    message: str


class CatalogList(BaseModel):
    """Wrapper for listing catalog entries."""

    entries: list[CatalogEntryRead]


class CatalogInstallRequest(BaseModel):
    """Payload for installing a catalog entry as a connection."""

    credential: str | None = Field(
        default=None,
        description="API key, PAT, or access token for auth_types that need one",
    )
    server_url: str | None = None
    account_identifier: str | None = None
    org_wide: bool = False
