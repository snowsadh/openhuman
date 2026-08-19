"""
Slack OAuth 2.0 flow — "Connect Slack" onboarding.

Endpoints
--------
GET /api/slack/install
    Redirect the user to Slack's OAuth authorize page.
    Query params: ``employee_id`` (UUID), ``org_id`` (UUID).

GET /api/slack/oauth/callback
    Handle the OAuth redirect from Slack.  Exchanges the temporary code for
    a bot token, encrypts it, stores it on the employee record, and redirects
    the browser back to the dashboard.

Identity modes
--------------
- **fixed** (default): Each employee type maps to a pre-registered Slack app
  with a fixed name (e.g. "Alison" for HR, "Alex" for Support).  The bot's
  ``client_id`` / ``client_secret`` come from the fixed bot registry.
- **shared** (legacy): One global Slack app for all employees.  Uses
  ``SLACK_CLIENT_ID`` / ``SLACK_CLIENT_SECRET`` from settings.
- **per_employee** (Pattern A, deprecated): Each employee has its own Slack app
  identity via a pre-provisioned ``SlackAppSlot``.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.activity.service import record_activity
from app.core.config import settings
from app.core.connections import SLACK_AUTHORIZE_URL
from app.core.database import async_session_factory
from app.core.oauth import (
    decode_oauth_state,
    encode_oauth_state,
    frontend_redirect,
    get_state_secret,
    STATE_MAX_AGE,
)
from app.core.security import decrypt_token, encrypt_token

# Ensure all model modules are imported before using relationship loaders
import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401
import app.agent.tools.mcp.models  # noqa: F401

from app.employees.models import Employee
from app.gateway.fixed_bots import get_fixed_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slack", tags=["slack"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Slack OAuth scopes the bot needs to function (Socket Mode + messaging).
_SLACK_BOT_SCOPES = [
    "app_mentions:read",
    "channels:history",
    "channels:join",
    "groups:history",
    "chat:write",
    "chat:write.customize",
    "files:read",
    "files:write",
    "im:history",
    "im:write",
    "mpim:history",
    "mpim:write",
    "users:read",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_oauth_state(employee_id: UUID, org_id: UUID, redirect_to: str | None = None) -> str:
    """Create a short-lived signed token for Slack OAuth state parameter."""
    return encode_oauth_state(
        "slack-oauth-state",
        employee_id=employee_id,
        org_id=org_id,
        redirect_to=redirect_to,
    )


def _decode_oauth_state(state: str) -> dict | None:
    """Decode and validate Slack OAuth state token."""
    payload = decode_oauth_state(
        "slack-oauth-state",
        state,
        required_fields={"employee_id", "org_id"},
    )
    if payload is None:
        logger.warning("Slack OAuth state token is invalid or expired")
    return payload


def _frontend_redirect(
    employee_id: str,
    success: bool,
    detail: str = "",
    redirect_to: str | None = None,
) -> RedirectResponse:
    """Build a redirect back to the frontend with a ``slack`` query param."""
    return frontend_redirect(
        employee_id,
        success,
        param_name="slack",
        detail=detail,
        redirect_to=redirect_to,
    )


def _build_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI from the request, handling proxy headers."""
    redirect_uri = settings.slack_oauth_redirect_uri
    if not redirect_uri or "<YOUR-RAILWAY-API-DOMAIN>" in redirect_uri:
        base_url = str(request.base_url).rstrip("/")
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        if proto == "https" and base_url.startswith("http://"):
            base_url = base_url.replace("http://", "https://")
        redirect_uri = f"{base_url}/api/slack/oauth/callback"
    return redirect_uri


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/install")
async def slack_install(
    request: Request,
    employee_id: str = Query(..., description="Employee UUID"),
    org_id: str = Query(..., description="Organization UUID"),
    redirect_to: str | None = Query(None, description="URL to redirect back to after callback"),
) -> RedirectResponse:
    """Redirect the browser to Slack's OAuth authorize page.

    The ``employee_id`` and ``org_id`` are baked into a signed state
    parameter so the callback can associate the token with the right
    employee.

    In **fixed** mode the authorize URL uses the fixed bot's client_id
    based on the employee's ``employee_type``.
    """
    # Validate UUIDs
    try:
        emp_uuid = UUID(employee_id)
        org_uuid = UUID(org_id)
    except ValueError:
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Invalid employee or organization ID.",
            redirect_to=redirect_to,
        )

    async with async_session_factory() as session:
        emp = await session.scalar(
            select(Employee).where(
                Employee.id == emp_uuid, Employee.org_id == org_uuid
            )
        )

    if emp is None:
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Employee not found.",
            redirect_to=redirect_to,
        )

    actual_redirect_to = redirect_to or f"{settings.frontend_url.rstrip('/')}/dashboard/{emp_uuid}"
    state = _encode_oauth_state(emp_uuid, org_uuid, actual_redirect_to)
    scope = ",".join(_SLACK_BOT_SCOPES)
    redirect_uri = _build_redirect_uri(request)

    if settings.slack_identity_mode == "fixed":
        # ---- Fixed mode: look up client_id from the fixed bot registry ----
        fixed_bot = get_fixed_bot(emp.employee_type) if emp.employee_type else None
        if fixed_bot is None or not fixed_bot.client_id:
            return _frontend_redirect(
                employee_id,
                success=False,
                detail=f"No fixed Slack bot configured for employee type '{emp.employee_type}'.",
                redirect_to=redirect_to,
            )
        client_id = fixed_bot.client_id

    elif settings.slack_identity_mode == "shared":
        # ---- Shared mode (legacy): global app ----
        if not settings.slack_client_id:
            logger.error("Slack OAuth is not configured (missing client_id).")
            return _frontend_redirect(
                employee_id,
                success=False,
                detail="Slack integration is not configured on this server.",
                redirect_to=redirect_to,
            )
        client_id = settings.slack_client_id

    else:
        # ---- per_employee (deprecated) — kept for backward compat ----
        logger.error("per_employee identity mode is deprecated. Use 'fixed' instead.")
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Slack identity mode 'per_employee' is deprecated.",
            redirect_to=redirect_to,
        )

    authorize_url = (
        f"{SLACK_AUTHORIZE_URL}"
        f"?client_id={client_id}"
        f"&scope={scope}"
        f"&state={state}"
        f"&redirect_uri={redirect_uri}"
    )

    logger.info(
        "Redirecting to Slack OAuth for employee %s (org %s, mode=%s)",
        employee_id,
        org_id,
        settings.slack_identity_mode,
    )

    # Record activity (best-effort)
    try:
        async with async_session_factory() as s:
            await record_activity(
                s,
                UUID(org_id),
                "slack_oauth",
                "Slack install started",
                employee_id=UUID(employee_id),
                employee_name=emp.name,
                platform="slack",
                metadata={"action": "install_initiated", "mode": settings.slack_identity_mode},
            )
    except Exception:
        pass

    return RedirectResponse(authorize_url, status_code=303)


@router.get("/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(..., description="Temporary OAuth code from Slack"),
    state: str = Query(..., description="State parameter echoed back by Slack"),
) -> RedirectResponse:
    """Handle the OAuth redirect from Slack.

    1. Validates the state JWT to recover employee / org.
    2. Exchanges the ``code`` for a bot token via Slack's API.
    3. Encrypts and stores the token on the employee record.
    4. Redirects the browser back to the employee's dashboard page.

    In **fixed** mode the exchange uses the fixed bot's client secret
    based on the employee's ``employee_type``.
    """
    # ---- 1. Validate state --------------------------------------------------
    payload = _decode_oauth_state(state)
    if payload is None:
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}/dashboard?slack=error&reason=invalid_state",
            status_code=303,
        )

    employee_id = payload["employee_id"]
    org_id = payload["org_id"]
    redirect_to = payload.get("redirect_to")

    async with async_session_factory() as session:
        emp = await session.scalar(
            select(Employee).where(
                Employee.id == UUID(employee_id),
                Employee.org_id == UUID(org_id),
            )
        )

    if emp is None:
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Employee no longer exists.",
            redirect_to=redirect_to,
        )

    # Determine which credentials to use
    redirect_uri = _build_redirect_uri(request)

    if settings.slack_identity_mode == "fixed":
        fixed_bot = get_fixed_bot(emp.employee_type) if emp.employee_type else None
        if fixed_bot is None or not fixed_bot.is_configured:
            return _frontend_redirect(
                employee_id,
                success=False,
                detail=f"No fixed Slack bot configured for type '{emp.employee_type}'.",
                redirect_to=redirect_to,
            )
        oauth_client_id = fixed_bot.client_id
        oauth_client_secret = fixed_bot.client_secret
        oauth_redirect_uri = redirect_uri

    elif settings.slack_identity_mode == "shared":
        if not settings.slack_client_id or not settings.slack_client_secret:
            logger.error("Slack OAuth config incomplete — cannot exchange code.")
            return _frontend_redirect(
                employee_id,
                success=False,
                detail="Slack integration is not fully configured.",
                redirect_to=redirect_to,
            )
        oauth_client_id = settings.slack_client_id
        oauth_client_secret = settings.slack_client_secret
        oauth_redirect_uri = redirect_uri

    else:
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Unsupported Slack identity mode.",
            redirect_to=redirect_to,
        )

    # ---- 2. Exchange code for token -----------------------------------------
    try:
        client = AsyncWebClient()
        oauth_response = await client.oauth_v2_access(
            client_id=oauth_client_id,
            client_secret=oauth_client_secret,
            code=code,
            redirect_uri=oauth_redirect_uri,
        )
    except Exception as exc:
        logger.exception("Slack OAuth token exchange failed")
        return _frontend_redirect(
            employee_id,
            success=False,
            detail=f"Token exchange failed: {exc}",
            redirect_to=redirect_to,
        )

    if not oauth_response.get("ok"):
        error_detail = oauth_response.get("error", "unknown_error")
        logger.error("Slack OAuth returned error: %s", error_detail)
        return _frontend_redirect(
            employee_id,
            success=False,
            detail=f"Slack rejected the request: {error_detail}",
            redirect_to=redirect_to,
        )

    bot_token = oauth_response.get("access_token")
    if not bot_token:
        logger.error("Slack OAuth response missing access_token")
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Slack did not return a bot token.",
            redirect_to=redirect_to,
        )

    # ---- 3. Store encrypted token + workspace metadata -----------------------
    try:
        encrypted = encrypt_token(bot_token)
    except Exception as exc:
        logger.exception("Failed to encrypt Slack bot token")
        return _frontend_redirect(
            employee_id,
            success=False,
            detail="Internal encryption error.",
            redirect_to=redirect_to,
        )

    async with async_session_factory() as session:
        emp = await session.scalar(
            select(Employee).where(
                Employee.id == UUID(employee_id),
                Employee.org_id == UUID(org_id),
            )
        )
        if emp is None:
            return _frontend_redirect(
                employee_id,
                success=False,
                detail="Employee no longer exists.",
                redirect_to=redirect_to,
            )

        emp.slack_token_enc = encrypted

        # Persist workspace metadata from OAuth response
        team = oauth_response.get("team", {})
        emp.slack_team_id = team.get("id")
        emp.slack_team_name = team.get("name")

        # Auto-activate the employee so the gateway picks it up
        if emp.status == "inactive":
            emp.status = "active"

        await session.commit()

        # Record activity (best-effort, inside session block)
        try:
            team_name = oauth_response.get("team", {}).get("name", "unknown")
            await record_activity(
                session,
                UUID(org_id),
                "slack_oauth",
                f"Slack integration connected (workspace: {team_name})",
                employee_id=UUID(employee_id),
                employee_name=emp.name,
                platform="slack",
                metadata={
                    "action": "oauth_complete",
                    "slack_team_id": oauth_response.get("team", {}).get("id"),
                    "slack_team_name": team_name,
                    "mode": settings.slack_identity_mode,
                },
            )
        except Exception:
            pass

    logger.info(
        "Slack OAuth complete — token stored for employee %s (team: %s, mode=%s)",
        employee_id,
        oauth_response.get("team", {}).get("name", "unknown"),
        settings.slack_identity_mode,
    )

    # ---- 4. Redirect to dashboard -------------------------------------------
    return _frontend_redirect(employee_id, success=True, redirect_to=redirect_to)
