"""Connector specification model — no internal imports, safe to import from anywhere."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

AuthType = Literal["none", "api_key_header", "pat_bearer", "oauth2"]
TransportType = Literal["streamable_http", "sse", "stdio"]


class ConnectorSpec(BaseModel):
    """Declarative description of a single MCP server.

    Adding a new connector means adding one instance of this model to the
    ``REGISTRY`` dict — no changes to the manager, router, or graph plumbing.
    """

    slug: str = Field(description="Unique key used in REGISTRY and DB lookups")
    name: str = Field(description="Human-readable display name")
    description: str = Field(description="One-sentence summary of what this connector provides")
    base_url: str | None = Field(
        default=None,
        description="MCP server endpoint for HTTP/SSE transports",
    )
    transport: TransportType = Field(
        default="streamable_http",
        description="Transport protocol used to communicate with the MCP server",
    )
    command: str | None = Field(
        default=None,
        description="Executable to launch when using stdio transport",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Arguments passed to the stdio MCP command",
    )
    auth_type: AuthType = Field(
        default="none", description="Primary authentication method for this server"
    )
    alternative_auth_types: list[AuthType] = Field(
        default_factory=list,
        description="Additional authentication methods users can choose from "
        "(e.g., ``['pat_bearer']`` for connectors that primarily use OAuth2)",
    )
    requires_custom_server_url: bool = Field(
        default=False,
        description="If True, the org must provide a per-connection MCP server URL instead of using a fixed registry base_url",
    )

    # Auth metadata (used by the OAuth router for oauth2 connectors)
    authorize_url: str | None = Field(default=None, description="OAuth2 authorization endpoint")
    token_url: str | None = Field(default=None, description="OAuth2 token exchange endpoint")
    default_scopes: list[str] = Field(default_factory=list, description="Recommended OAuth scopes")
    docs_url: str = Field(default="", description="Link to developer docs for this MCP server")

    # Tool filtering — restrict tools server-side before they reach the LLM
    default_tool_allow: list[str] | None = Field(
        default=None,
        description="If set, ONLY these tool names are kept (before prefixing); "
        "``None`` means allow all tools discovered from this server",
    )
    default_tool_deny: list[str] = Field(
        default_factory=list,
        description="Tool names to exclude from the discovered tool set",
    )

    # ------------------------------------------------------------------
    # Hardening (Phase 4)
    # ------------------------------------------------------------------
    request_timeout_seconds: float = Field(
        default=30.0,
        description="Per-request timeout for tool loading and tool calls to this server",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        description="Max MCP tool calls per minute to this server (0 = unlimited)",
    )

    # Token auth method for OAuth token exchange
    token_auth_method: Literal["form", "basic"] = Field(
        default="form",
        description="How to send client credentials to the token endpoint: "
        "'form' = POST body fields (default), 'basic' = HTTP Basic Auth header",
    )

    # Feature flags
    supports_token_refresh: bool = Field(
        default=False, description="True if the server issues OAuth refresh tokens"
    )
    requires_manual_approval: bool = Field(
        default=False,
        description="True if the vendor must approve custom integrations before use",
    )

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "ConnectorSpec":
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio connectors require a command")
        elif not self.base_url and not self.requires_custom_server_url:
            raise ValueError(
                "HTTP/SSE connectors require a base_url unless they require a custom server URL"
            )
        return self
