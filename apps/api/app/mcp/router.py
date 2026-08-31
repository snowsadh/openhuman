"""MCP management API — list registry, connect/disconnect, OAuth flows."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import quote_plus, urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity
from app.agent.armoriq import agent_id_for_employee_kind, mint_intent_token
from app.agent.tools.mcp.catalog import (
    build_connector_spec,
    get_catalog_entry,
    is_hardcoded,
    list_catalog,
)
from app.agent.tools.mcp.client import MCPClientManager, ResolvedConnection
from app.agent.tools.mcp.connectors import REGISTRY
from app.agent.tools.mcp.models import McpConnection
from app.agent.tools.mcp.security import validate_connector_config
from app.auth.models import User
from app.core.config import settings
from app.core.database import async_session_factory, get_db
from app.core.dependencies import get_current_user
from app.core.security import decrypt_token, encrypt_token
from app.employees.models import Employee
from app.mcp.oauth import (
    _decode_oauth_state,
    _frontend_redirect,
    build_authorize_url,
    exchange_code,
)
from app.mcp.schemas import (
    CatalogEntryRead,
    CatalogInstallRequest,
    CatalogList,
    ConnectorStatus,
    McpConnectionCreate,
    McpConnectionList,
    McpConnectionRead,
    McpVerificationRequest,
    McpVerificationResponse,
)
from app.organizations.models import Organization

logger = logging.getLogger(__name__)


def _connection_read(connection: McpConnection) -> McpConnectionRead:
    return McpConnectionRead(
        id=connection.id,
        connector_slug=connection.connector_slug,
        auth_type=connection.auth_type,
        scopes=connection.scopes,
        status=connection.status,
        verification_status=connection.verification_status,
        discovered_tools=connection.discovered_tools,
        discovered_tool_count=connection.discovered_tool_count,
        verification_error=connection.verification_error,
        last_verified_at=connection.last_verified_at,
        oauth_expires_at=connection.oauth_expires_at,
        is_org_wide=connection.employee_id is None,
        last_used_at=connection.last_used_at,
        created_at=connection.created_at,
    )


async def _require_owned_employee(
    db: AsyncSession,
    org_id: UUID,
    emp_id: UUID,
    user: User,
) -> Employee:
    employee = await db.scalar(
        select(Employee)
        .join(Organization, Organization.id == Employee.org_id)
        .where(
            Employee.id == emp_id,
            Employee.org_id == org_id,
            Organization.owner_id == user.id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


def _safe_verification_error(exc: Exception, credential: str | None) -> str:
    detail = str(exc).strip().replace("\n", " ")[:300]
    if credential:
        detail = detail.replace(credential, "[REDACTED]")
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


def _normalize_server_url(server_url: str | None) -> str | None:
    if server_url is None:
        return None

    normalized = server_url.strip()
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="server_url must be a valid http(s) MCP endpoint URL",
        )

    return normalized.rstrip("/")


# -- org/employee-scoped CRUD router -----------------------------------------
router = APIRouter(prefix="/api/organizations/{org_id}", tags=["mcp"])

# -- standalone OAuth callback router (no org prefix) -------------------------
oauth_router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# List registry + connection status
# ---------------------------------------------------------------------------


@router.get("/mcp-connectors", response_model=list[ConnectorStatus])
async def list_mcp_connectors(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[ConnectorStatus]:
    """Return every connector in the registry with its connection count
    for this organization."""
    # Count connections per slug for this org
    organization = await db.scalar(
        select(Organization).where(
            Organization.id == org_id, Organization.owner_id == _current_user.id
        )
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result = await db.execute(
        select(
            McpConnection.connector_slug,
            McpConnection.status,
        ).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
        )
    )
    connected_slugs: set[str] = {row.connector_slug for row in result}

    # Count per slug
    result2 = await db.execute(
        select(McpConnection.connector_slug).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
        )
    )
    counts: dict[str, int] = {}
    for row in result2:
        counts[row.connector_slug] = counts.get(row.connector_slug, 0) + 1

    verified_result = await db.execute(
        select(McpConnection.connector_slug).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
            McpConnection.verification_status == "verified",
        )
    )
    verified_counts: dict[str, int] = {}
    for row in verified_result:
        verified_counts[row.connector_slug] = verified_counts.get(row.connector_slug, 0) + 1

    output: list[ConnectorStatus] = []
    for slug, spec in REGISTRY.items():
        auth_types = [spec.auth_type] + [
            a for a in spec.alternative_auth_types if a != spec.auth_type
        ]
        output.append(
            ConnectorStatus(
                slug=slug,
                name=spec.name,
                description=spec.description,
                auth_type=spec.auth_type,
                auth_types=auth_types,
                docs_url=spec.docs_url,
                requires_custom_server_url=spec.requires_custom_server_url,
                is_connected=slug in connected_slugs,
                connection_count=counts.get(slug, 0),
                verified_connection_count=verified_counts.get(slug, 0),
                verification_status=("verified" if verified_counts.get(slug, 0) else "unverified"),
            )
        )

    return output


# ---------------------------------------------------------------------------
# Employee MCP connections CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/employees/{emp_id}/mcp-connections",
    response_model=McpConnectionList,
)
async def list_employee_mcp_connections(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> McpConnectionList:
    """List active MCP connections available to *emp_id* (theirs + org-wide)."""
    await _require_owned_employee(db, org_id, emp_id, _current_user)
    result = await db.execute(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
            ((McpConnection.employee_id == emp_id) | (McpConnection.employee_id.is_(None))),
        )
    )
    rows = list(result.scalars().all())

    connections: list[McpConnectionRead] = []
    for row in rows:
        connections.append(_connection_read(row))

    return McpConnectionList(connections=connections)


@router.post(
    "/employees/{emp_id}/mcp-connections/{slug}",
    response_model=McpConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_connection(
    org_id: UUID,
    emp_id: UUID,
    slug: str,
    data: McpConnectionCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> McpConnectionRead:
    """Create or update an API-key / PAT MCP connection for *emp_id*.

    The credential is encrypted at rest via AES-256-GCM.
    """
    await _require_owned_employee(db, org_id, emp_id, _current_user)

    # Validate connector slug
    spec = REGISTRY.get(slug)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown connector slug: {slug}",
        )

    supported_for_paste = {"api_key_header", "pat_bearer", "none"}
    supported_auth_types = [
        spec.auth_type,
        *[alt for alt in spec.alternative_auth_types if alt != spec.auth_type],
    ]
    paste_auth_types = [
        auth_type for auth_type in supported_auth_types if auth_type in supported_for_paste
    ]

    selected_auth_type = data.auth_type
    if selected_auth_type:
        if selected_auth_type not in supported_auth_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Connector '{slug}' does not support auth_type='{selected_auth_type}'. "
                    f"Supported auth types: {', '.join(supported_auth_types)}"
                ),
            )
        if selected_auth_type not in supported_for_paste:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"auth_type='{selected_auth_type}' for connector '{slug}' "
                    "requires the OAuth install flow."
                ),
            )
    else:
        if spec.auth_type in supported_for_paste:
            selected_auth_type = spec.auth_type
        elif paste_auth_types:
            # This endpoint is specifically for pasted credentials, so when a
            # connector's primary auth is OAuth but it supports PAT/API-key
            # auth as an alternative (for example Notion), default to the first
            # paste-friendly mode.
            selected_auth_type = paste_auth_types[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Connector '{slug}' uses auth_type={spec.auth_type} "
                    "and does not list an alternative paste-friendly auth type. "
                    "Use the OAuth install flow for oauth2 connectors."
                ),
            )

    normalized_server_url = _normalize_server_url(data.server_url)
    if spec.requires_custom_server_url and not normalized_server_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connector '{slug}' requires a server_url (for example your n8n MCP endpoint)",
        )

    # -- Security validation gate (save-time) ----------------------------
    security_issues = validate_connector_config(
        slug,
        spec,
        server_url=normalized_server_url,
        credentials=data.credential,
    )
    if security_issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"slug": slug, "security_issues": security_issues},
        )

    # Encrypt the credential
    try:
        encrypted = encrypt_token(data.credential)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt credential",
        ) from exc

    # Upsert: if a connection for this org/employee/slug already exists,
    # update it rather than creating a duplicate.
    existing = await db.scalar(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.employee_id == emp_id,
            McpConnection.connector_slug == slug,
        )
    )

    if existing is not None:
        existing.credentials_enc = encrypted
        existing.auth_type = selected_auth_type
        existing.server_url = normalized_server_url
        existing.scopes = data.scopes
        existing.status = "connected"
        existing.verification_status = "unverified"
        existing.discovered_tools = None
        existing.discovered_tool_count = 0
        existing.verification_error = None
        existing.last_verified_at = None
        conn = existing
        is_new = False
    else:
        conn = McpConnection(
            org_id=org_id,
            employee_id=None if data.org_wide else emp_id,
            connector_slug=slug,
            auth_type=selected_auth_type,
            credentials_enc=encrypted,
            server_url=normalized_server_url,
            scopes=data.scopes,
            status="connected",
            connected_by_user_id=_current_user.id,
        )
        db.add(conn)
        is_new = True

    await db.commit()
    await db.refresh(conn)

    logger.info(
        "%s MCP connection '%s' for employee %s in org %s",
        "Created" if is_new else "Updated",
        slug,
        emp_id,
        org_id,
    )

    # Record activity (best-effort)
    try:
        emp = await db.get(Employee, emp_id)
        await record_activity(
            db,
            org_id,
            "mcp_connected",
            f"{'Connected' if is_new else 'Updated'} {slug} MCP tool",
            employee_id=emp_id,
            employee_name=emp.name if emp else None,
            platform="api",
            metadata={
                "action": "create" if is_new else "update",
                "connector_slug": slug,
                "auth_type": selected_auth_type,
                "server_url": normalized_server_url,
            },
        )
    except Exception:
        pass

    return _connection_read(conn)


@router.post(
    "/employees/{emp_id}/mcp-connections/{slug}/verify",
    response_model=McpVerificationResponse,
)
async def verify_mcp_connection(
    org_id: UUID,
    emp_id: UUID,
    slug: str,
    data: McpVerificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> McpVerificationResponse:
    """Run tools/list and, when requested, one exact read call through ArmorIQ.

    Discovery alone produces ``discovered``. A connector becomes ``verified``
    only after the selected tool executes through the signed intent boundary.
    """
    employee = await _require_owned_employee(db, org_id, emp_id, current_user)
    connection = await db.scalar(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.connector_slug == slug,
            McpConnection.status == "connected",
            ((McpConnection.employee_id == emp_id) | (McpConnection.employee_id.is_(None))),
        )
    )
    spec = REGISTRY.get(slug)
    if connection is None or spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    credential: str | None = None
    manager = MCPClientManager()
    try:
        if connection.credentials_enc:
            credential = decrypt_token(connection.credentials_enc)
        resolved = ResolvedConnection(
            slug=slug,
            connector=spec,
            credentials=credential,
            auth_type=connection.auth_type,
            server_url=connection.server_url,
        )
        tools = await manager.connect([resolved])
        discovered = sorted(tool.name.split("__", 2)[-1] for tool in tools)
        if not discovered:
            raise RuntimeError("MCP server returned no usable tools from tools/list")

        connection.discovered_tools = discovered
        connection.discovered_tool_count = len(discovered)
        connection.last_verified_at = datetime.now(UTC)
        connection.verification_error = None
        connection.verification_status = "discovered"
        probe_executed = False

        if data.probe_tool:
            prefixed_name = f"mcp__{slug}__{data.probe_tool}"
            tool = next(
                (item for item in tools if item.name in {data.probe_tool, prefixed_name}),
                None,
            )
            if tool is None:
                raise ValueError(f"Probe tool '{data.probe_tool}' was not returned by tools/list")
            token = await asyncio.to_thread(
                mint_intent_token,
                prompt=f"Verify read-only {slug}.{data.probe_tool} connection",
                steps=[
                    {
                        "mcp": slug,
                        "action": data.probe_tool,
                        "tool": data.probe_tool,
                        "params": data.probe_parameters,
                        "description": f"Verify {slug}.{data.probe_tool}",
                    }
                ],
                user_email=current_user.email,
                metadata={
                    "employee_id": str(emp_id),
                    "organization_id": str(org_id),
                    "agent_id": agent_id_for_employee_kind(employee.employee_type),
                    "platform": "mcp-verification",
                },
            )
            await tool.ainvoke(
                data.probe_parameters,
                config={
                    "configurable": {
                        "armoriq_intent_token": token.model_dump(mode="json"),
                        "armoriq_user_email": current_user.email,
                        "armoriq_agent_id": agent_id_for_employee_kind(employee.employee_type),
                        "employee_id": str(emp_id),
                        "org_id": str(org_id),
                        "platform": "mcp-verification",
                    }
                },
            )
            connection.verification_status = "verified"
            probe_executed = True

        await db.commit()
        await db.refresh(connection)
        return McpVerificationResponse(
            connection=_connection_read(connection),
            discovered_tools=discovered,
            probe_executed=probe_executed,
            message=(
                "Verified through ArmorIQ"
                if probe_executed
                else "Tool discovery succeeded; run a read probe to verify execution"
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        connection.verification_status = "error"
        connection.verification_error = _safe_verification_error(exc, credential)
        connection.last_verified_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"slug": slug, "verification_error": connection.verification_error},
        ) from exc
    finally:
        await manager.disconnect()


@router.delete(
    "/employees/{emp_id}/mcp-connections/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_mcp_connection(
    org_id: UUID,
    emp_id: UUID,
    slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> None:
    """Revoke (mark as 'revoked') an employee's MCP connection.

    The row is kept for audit purposes; credentials are not removed but
    will no longer be resolved.
    """
    await _require_owned_employee(db, org_id, emp_id, _current_user)
    conn = await db.scalar(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.employee_id == emp_id,
            McpConnection.connector_slug == slug,
        )
    )

    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No connection found for slug '{slug}'",
        )

    conn.status = "revoked"
    conn.verification_status = "unverified"
    await db.commit()

    logger.info(
        "Revoked MCP connection '%s' for employee %s in org %s",
        slug,
        emp_id,
        org_id,
    )

    # Record activity (best-effort)
    try:
        emp = await db.get(Employee, emp_id)
        await record_activity(
            db,
            org_id,
            "mcp_connected",
            f"Revoked {slug} MCP connection",
            employee_id=emp_id,
            employee_name=emp.name if emp else None,
            platform="api",
            metadata={
                "action": "revoke",
                "connector_slug": slug,
            },
        )
    except Exception:
        pass


# ===========================================================================
# OAuth install — redirect the browser to the provider's consent page
# ===========================================================================


@router.get(
    "/employees/{emp_id}/mcp-connections/{slug}/install",
    summary="Start OAuth install for an MCP connector",
)
async def mcp_oauth_install(
    org_id: UUID,
    emp_id: UUID,
    slug: str,
    redirect_to: str | None = Query(
        None, description="URL to redirect back to after the OAuth callback"
    ),
    client_id: str | None = Query(
        None, description="Override OAuth client_id (for connectors without hardcoded credentials)"
    ),
    client_secret: str | None = Query(None, description="Override OAuth client_secret"),
    authorize_url: str | None = Query(
        None, description="Override OAuth authorize_url (for connectors without hardcoded URLs)"
    ),
    token_url: str | None = Query(None, description="Override OAuth token_url"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RedirectResponse:
    """Redirect the browser to the OAuth provider's authorize page.

    The employee / org / connector are baked into a JWT-signed ``state``
    parameter so the callback can associate the tokens with the right
    record — no server-side session needed.

    For connectors that don't have hardcoded OAuth URLs or client credentials
    (e.g. catalog-only entries like figma, jira, etc.), pass ``client_id``,
    ``client_secret``, ``authorize_url``, and ``token_url`` as query parameters.
    """
    # -- Validate connector ---------------------------------------------------
    spec = REGISTRY.get(slug)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown connector slug: {slug}",
        )

    # Allow caller to override OAuth URLs (for catalog-only connectors)
    effective_authorize = authorize_url or spec.authorize_url
    effective_token = token_url or spec.token_url

    if not effective_authorize:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Connector '{slug}' does not support OAuth (no authorize_url "
                "configured in its spec). "
                "Pass authorize_url and client_id as query params, or use a "
                "paste-friendly auth method."
            ),
        )

    # -- Verify the employee exists -------------------------------------------
    emp = await db.scalar(
        select(Employee).where(
            Employee.id == emp_id,
            Employee.org_id == org_id,
        )
    )
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # -- Build & redirect -----------------------------------------------------
    try:
        auth_url = build_authorize_url(
            spec,
            emp_id,
            org_id,
            redirect_to,
            override_authorize_url=effective_authorize,
            override_token_url=effective_token,
            override_client_id=client_id,
            override_client_secret=client_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info(
        "Redirecting to %s OAuth for employee %s (org %s)",
        slug,
        emp_id,
        org_id,
    )

    # Record activity (best-effort)
    try:
        await record_activity(
            db,
            org_id,
            "mcp_connected",
            f"OAuth install started for {slug}",
            employee_id=emp_id,
            employee_name=emp.name,
            platform="api",
            metadata={
                "action": "oauth_install",
                "connector_slug": slug,
            },
        )
    except Exception:
        pass

    return RedirectResponse(auth_url, status_code=303)


# ===========================================================================
# OAuth callback — handle the redirect from the provider
# ===========================================================================


@oauth_router.get(
    "/oauth/callback",
    summary="OAuth callback for MCP connectors",
)
async def mcp_oauth_callback(
    code: str = Query(..., description="Temporary OAuth code from the provider"),
    state: str = Query(..., description="State parameter echoed back by the provider"),
    error: str | None = Query(None, description="OAuth error, if the user declined"),
    error_description: str | None = Query(
        None, description="Human-readable OAuth error description"
    ),
) -> RedirectResponse:
    """Handle the OAuth redirect from an MCP provider.

    1. Validates the state JWT to recover employee / org / connector.
    2. Exchanges the ``code`` for access + refresh tokens.
    3. Encrypts and stores the tokens in the ``mcp_connections`` table.
    4. Redirects the browser back to the frontend with outcome params.
    """
    # -- Handle provider-reported errors (user declined, etc.) -----------------
    if error:
        logger.warning("MCP OAuth provider returned error: %s — %s", error, error_description)
        # Try to decode state so we can redirect back with context
        payload = _decode_oauth_state(state)
        if payload:
            return _frontend_redirect(
                payload["employee_id"],
                payload["connector_slug"],
                success=False,
                detail=error_description or error,
                redirect_to=payload.get("redirect_to"),
            )
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}/?mcp_oauth=error"
            f"&reason={quote_plus(error_description or error)}",
            status_code=303,
        )

    # -- 1. Validate state JWT ------------------------------------------------
    payload = _decode_oauth_state(state)
    if payload is None:
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}/?mcp_oauth=error"
            f"&reason={quote_plus('Invalid or expired OAuth state. Please try again.')}",
            status_code=303,
        )

    employee_id = payload["employee_id"]
    org_id = payload["org_id"]
    connector_slug = payload["connector_slug"]
    redirect_to = payload.get("redirect_to")

    # -- 2. Look up the connector spec ----------------------------------------
    spec = REGISTRY.get(connector_slug)
    if spec is None:
        return _frontend_redirect(
            employee_id,
            connector_slug,
            success=False,
            detail=f"Unknown connector: {connector_slug}",
            redirect_to=redirect_to,
        )

    code_verifier = payload.get("code_verifier")
    # Pull overrides from state (set by catalog-only OAuth connectors)
    oauth_token_url = payload.get("token_url") or None
    oauth_client_id = payload.get("client_id_override") or None
    oauth_client_secret = payload.get("client_secret") or None

    # -- 3. Exchange the code for tokens --------------------------------------
    try:
        token_data = await exchange_code(
            spec,
            code,
            code_verifier=code_verifier,
            override_token_url=oauth_token_url,
            override_client_id=oauth_client_id,
            override_client_secret=oauth_client_secret,
        )
    except Exception as exc:
        logger.exception("OAuth token exchange failed for %s", connector_slug)
        return _frontend_redirect(
            employee_id,
            connector_slug,
            success=False,
            detail=f"Token exchange failed: {exc}",
            redirect_to=redirect_to,
        )

    # -- 4. Encrypt & store ---------------------------------------------------
    try:
        encrypted_access = encrypt_token(token_data["access_token"])
        encrypted_refresh = (
            encrypt_token(token_data["refresh_token"]) if token_data.get("refresh_token") else None
        )
    except Exception:
        logger.exception("Failed to encrypt OAuth tokens for %s", connector_slug)
        return _frontend_redirect(
            employee_id,
            connector_slug,
            success=False,
            detail="Internal encryption error.",
            redirect_to=redirect_to,
        )

    # Upsert — re-installing the same connector updates the existing row.
    async with async_session_factory() as session:
        existing = await session.scalar(
            select(McpConnection).where(
                McpConnection.org_id == UUID(org_id),
                McpConnection.employee_id == UUID(employee_id),
                McpConnection.connector_slug == connector_slug,
            )
        )

        granted_scopes: list[str] | None = None
        if "scope" in token_data:
            granted_scopes = (
                token_data["scope"].split()
                if isinstance(token_data["scope"], str)
                else token_data["scope"]
            )

        if existing is not None:
            existing.credentials_enc = encrypted_access
            existing.oauth_refresh_token_enc = encrypted_refresh
            existing.auth_type = "oauth2"
            existing.scopes = granted_scopes or spec.default_scopes
            existing.status = "connected"
            existing.verification_status = "unverified"
            existing.discovered_tools = None
            existing.discovered_tool_count = 0
            existing.verification_error = None
            existing.last_verified_at = None
        else:
            conn = McpConnection(
                org_id=UUID(org_id),
                employee_id=UUID(employee_id),
                connector_slug=connector_slug,
                auth_type="oauth2",
                credentials_enc=encrypted_access,
                oauth_refresh_token_enc=encrypted_refresh,
                scopes=granted_scopes or spec.default_scopes,
                status="connected",
            )
            session.add(conn)

        await session.commit()

        # Record activity (best-effort, inside the session block)
        try:
            await record_activity(
                session,
                UUID(org_id),
                "mcp_connected",
                f"{connector_slug} MCP OAuth complete",
                employee_id=UUID(employee_id),
                platform="api",
                metadata={
                    "action": "oauth_complete",
                    "connector_slug": connector_slug,
                },
            )
        except Exception:
            pass

    logger.info(
        "MCP OAuth complete — %s tokens stored for employee %s (org %s)",
        connector_slug,
        employee_id,
        org_id,
    )

    # -- 5. Redirect to frontend ----------------------------------------------
    return _frontend_redirect(
        employee_id,
        connector_slug,
        success=True,
        redirect_to=redirect_to,
    )


# ===========================================================================
# Catalog — discover and install marketplace MCP servers
# ===========================================================================


@router.get("/mcp-catalog", response_model=CatalogList)
async def list_catalog_entries(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> CatalogList:
    """Return every catalog entry with its install status for this org."""
    organization = await db.scalar(
        select(Organization).where(
            Organization.id == org_id, Organization.owner_id == _current_user.id
        )
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result = await db.execute(
        select(
            McpConnection.connector_slug,
            McpConnection.verification_status,
        ).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
        )
    )
    connection_states: dict[str, str] = {
        row.connector_slug: row.verification_status for row in result
    }

    entries: list[CatalogEntryRead] = []
    for entry in list_catalog():
        entries.append(
            CatalogEntryRead(
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                category=entry.category,
                auth_type=entry.auth_type,
                docs_url=entry.docs_url,
                is_hardcoded=is_hardcoded(entry.slug),
                is_installed=entry.slug in REGISTRY and entry.slug in connection_states,
                catalog_state=entry.catalog_state,
                is_installable=entry.is_installable,
                verification_status=connection_states.get(entry.slug, "unverified"),
            )
        )

    return CatalogList(entries=entries)


@router.post(
    "/employees/{emp_id}/mcp-catalog/{slug}/install",
    response_model=McpConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def install_catalog_entry(
    org_id: UUID,
    emp_id: UUID,
    slug: str,
    data: CatalogInstallRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> McpConnectionRead:
    """Install a catalog MCP entry as a connection for *emp_id*.

    If the entry's ``ConnectorSpec`` is not yet in the ``REGISTRY``,
    this auto-generates and registers one on the fly.
    """
    entry = get_catalog_entry(slug)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown catalog entry: {slug}",
        )
    if not entry.is_installable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Catalog entry '{slug}' is {entry.catalog_state} and cannot be installed "
                "until its endpoint, authentication, and tools are verified."
            ),
        )

    await _require_owned_employee(db, org_id, emp_id, _current_user)

    if slug not in REGISTRY:
        spec = build_connector_spec(entry)
        REGISTRY[slug] = spec

    spec = REGISTRY[slug]

    # Determine auth type
    auth_type = entry.auth_type

    # Build the inner McpConnectionCreate from the request
    normalized_server_url = _normalize_server_url(data.server_url) if data.server_url else None

    # Validate security
    security_issues = validate_connector_config(
        slug,
        spec,
        server_url=normalized_server_url,
        credentials=data.credential if data.auth_type != "oauth2" else None,
    )
    if security_issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"slug": slug, "security_issues": security_issues},
        )

    # Pastable credentials (API key, PAT, none)
    if auth_type in ("api_key", "pat", "pat_bearer", "none"):
        encrypted = encrypt_token(data.credential) if data.credential else None

        existing = await db.scalar(
            select(McpConnection).where(
                McpConnection.org_id == org_id,
                McpConnection.employee_id == emp_id,
                McpConnection.connector_slug == slug,
            )
        )

        if existing is not None:
            if encrypted:
                existing.credentials_enc = encrypted
            existing.server_url = normalized_server_url
            existing.status = "connected"
            existing.verification_status = "unverified"
            existing.discovered_tools = None
            existing.discovered_tool_count = 0
            existing.verification_error = None
            existing.last_verified_at = None
            conn = existing
        else:
            conn = McpConnection(
                org_id=org_id,
                employee_id=None if data.org_wide else emp_id,
                connector_slug=slug,
                auth_type=auth_type,
                credentials_enc=encrypted,
                server_url=normalized_server_url,
                status="connected",
                connected_by_user_id=_current_user.id,
            )
            db.add(conn)

        await db.commit()
        await db.refresh(conn)

        logger.info("Installed catalog MCP '%s' for employee %s (org %s)", slug, emp_id, org_id)

        return _connection_read(conn)

    # OAuth2 — redirect to the OAuth install flow
    if auth_type == "oauth2":
        if not spec.authorize_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Catalog entry '{slug}' has no OAuth authorize URL configured",
            )
        from app.mcp.oauth import build_authorize_url as build_oauth_url

        auth_url = build_oauth_url(spec, emp_id, org_id, None)
        from fastapi.responses import RedirectResponse

        return RedirectResponse(auth_url, status_code=303)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported auth_type '{auth_type}' for catalog install",
    )
