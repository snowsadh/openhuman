"""Normalized MCP connections table — replaces the loose JSONB column on Employee."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class McpConnection(Base):
    __tablename__ = "mcp_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('connected', 'error', 'revoked')",
            name="ck_mcp_connections_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    org_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL = org-wide connection available to all employees",
    )
    connector_slug: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Matches a key in the connector REGISTRY"
    )
    auth_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="none | api_key_header | pat_bearer | oauth2",
    )

    # Encrypted secrets — AES-256-GCM via encrypt_token / decrypt_token
    credentials_enc: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Encrypted API key, PAT, or OAuth access token"
    )
    oauth_refresh_token_enc: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Encrypted OAuth2 refresh token"
    )
    server_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="Optional per-connection MCP server URL override"
    )

    scopes: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="Granted OAuth scopes (or configured scopes)"
    )

    status: Mapped[str] = mapped_column(String(50), default="connected", server_default="connected")

    connected_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
