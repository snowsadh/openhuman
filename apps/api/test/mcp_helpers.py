"""Shared MCP helpers for CLI and Streamlit test tools.

Provides MCP connection management and tool resolution that mirrors the
production ``app/agent/router.py`` logic but works with SQLite test databases.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.agent.tools.mcp.client import MCPClientManager, ResolvedConnection
from app.agent.tools.mcp.connectors import REGISTRY, ConnectorSpec
from app.agent.tools.mcp.models import McpConnection
from app.core.security import decrypt_token, encrypt_token
from app.employees.templates import get_template

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


async def list_mcp_connectors(
    session: AsyncSession,
    org_id: UUID,
    employee_id: UUID | None = None,
) -> list[dict]:
    """Return every connector in the registry with connection status for *org_id*.

    Each returned dict has keys: slug, name, description, auth_type, docs_url,
    is_connected, connection_id, status.
    """
    # Fetch all connections for this org + optional employee
    clauses = [
        McpConnection.org_id == org_id,
        McpConnection.status == "connected",
    ]
    if employee_id is not None:
        clauses.append(
            (McpConnection.employee_id == employee_id) | (McpConnection.employee_id.is_(None))
        )
    else:
        clauses.append(McpConnection.employee_id.is_(None))

    result = await session.execute(select(McpConnection).where(*clauses))
    connections: dict[str, McpConnection] = {
        row.connector_slug: row for row in result.scalars().all()
    }

    rows: list[dict] = []
    for slug, spec in REGISTRY.items():
        conn = connections.get(slug)
        rows.append(
            {
                "slug": slug,
                "name": spec.name,
                "description": spec.description,
                "auth_type": spec.auth_type,
                "docs_url": spec.docs_url,
                "is_connected": conn is not None,
                "connection_id": str(conn.id) if conn else None,
                "connection_status": conn.status if conn else "not_connected",
                "scopes": conn.scopes if conn else None,
                "requires_manual_approval": spec.requires_manual_approval,
            }
        )

    return rows


async def add_mcp_connection(
    session: AsyncSession,
    org_id: UUID,
    employee_id: UUID | None,
    slug: str,
    credential: str,
    scopes: list[str] | None = None,
    connected_by_user_id: UUID | None = None,
) -> McpConnection:
    """Create or update a PAT / API-key MCP connection.

    The *credential* is encrypted at rest with AES-256-GCM before storage.
    """
    spec = REGISTRY.get(slug)
    if spec is None:
        raise ValueError(f"Unknown connector slug: {slug}")

    if spec.auth_type not in ("pat_bearer", "api_key_header", "none"):
        raise ValueError(
            f"Connector '{slug}' uses auth_type={spec.auth_type}. "
            f"Use the OAuth install flow instead."
        )

    # Upsert: update existing if present
    existing = await session.scalar(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.employee_id == employee_id,
            McpConnection.connector_slug == slug,
        )
    )

    encrypted = encrypt_token(credential)

    if existing is not None:
        existing.credentials_enc = encrypted
        existing.auth_type = spec.auth_type
        existing.scopes = scopes
        existing.status = "connected"
        conn = existing
    else:
        conn = McpConnection(
            org_id=org_id,
            employee_id=employee_id,
            connector_slug=slug,
            auth_type=spec.auth_type,
            credentials_enc=encrypted,
            scopes=scopes,
            status="connected",
            connected_by_user_id=connected_by_user_id,
        )
        session.add(conn)

    await session.commit()
    await session.refresh(conn)
    return conn


async def remove_mcp_connection(
    session: AsyncSession,
    org_id: UUID,
    employee_id: UUID | None,
    slug: str,
) -> bool:
    """Soft-delete (revoke) an MCP connection.  Returns True if one was found."""
    conn = await session.scalar(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.employee_id == employee_id,
            McpConnection.connector_slug == slug,
            McpConnection.status == "connected",
        )
    )
    if conn is None:
        return False

    conn.status = "revoked"
    await session.commit()
    return True


async def get_mcp_connections_for_employee(
    session: AsyncSession,
    org_id: UUID,
    employee_id: UUID,
) -> list[McpConnection]:
    """Return all active MCP connections visible to *employee_id*.

    Includes both employee-specific rows and org-wide rows.
    """
    result = await session.execute(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
            ((McpConnection.employee_id == employee_id) | (McpConnection.employee_id.is_(None))),
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tool resolution (mirrors app/agent/router.py:_resolve_mcp_tools)
# ---------------------------------------------------------------------------


async def resolve_mcp_tools(
    session: AsyncSession,
    org_id: UUID,
    employee_id: UUID,
    allowed_mcp_servers: list[str],
) -> list:
    """Resolve MCP tools available to *employee_id*.

    1. Queries ``mcp_connections`` for org-wide + employee-specific rows.
    2. Filters by template ``allowed_mcp_servers``.
    3. Decrypts credentials and loads tools via ``MCPClientManager``.
    """
    if not allowed_mcp_servers:
        return []

    rows = await get_mcp_connections_for_employee(session, org_id, employee_id)
    if not rows:
        return []

    resolved: list[ResolvedConnection] = []
    for row in rows:
        # Template gate
        if "*" not in allowed_mcp_servers and row.connector_slug not in allowed_mcp_servers:
            continue

        spec = REGISTRY.get(row.connector_slug)
        if spec is None:
            logger.warning(
                "MCP connection references unknown connector slug '%s' — skipping",
                row.connector_slug,
            )
            continue

        # -- Lazy OAuth token refresh ---------------------------------------
        if (
            spec.supports_token_refresh
            and row.auth_type == "oauth2"
            and row.oauth_refresh_token_enc
        ):
            try:
                from app.mcp.oauth import refresh_access_token

                refreshed = await refresh_access_token(spec, row)
                if refreshed is not None:
                    await session.commit()
            except Exception:
                logger.debug(
                    "Token refresh not attempted / failed for %s",
                    row.connector_slug,
                )

        # Decrypt credentials
        creds: str | None = None
        if row.credentials_enc:
            try:
                creds = decrypt_token(row.credentials_enc)
            except Exception:
                logger.exception(
                    "Failed to decrypt credentials for MCP connection '%s'",
                    row.connector_slug,
                )
                continue

        resolved.append(
            ResolvedConnection(
                slug=row.connector_slug,
                connector=spec,
                credentials=creds,
                auth_type=row.auth_type,
                server_url=row.server_url,
            )
        )

    if not resolved:
        return []

    mgr = MCPClientManager()
    try:
        tools = await mgr.connect(resolved)
    except Exception:
        logger.exception("Failed to connect to MCP servers")
        tools = []

    return tools
