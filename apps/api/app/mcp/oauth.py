"""Reusable MCP OAuth 2.0 helper — install redirect + code exchange + token refresh.

Generalizes the Slack OAuth pattern (`app/gateway/slack_oauth.py`) so every
OAuth-based MCP connector shares the same plumbing:

* ``build_authorize_url`` — redirect the browser to the provider's consent page.
* ``exchange_code`` — trade the temporary code for access + refresh tokens.
* ``refresh_access_token`` — lazily refresh an expired OAuth2 access token.
* Signed ``state`` parameter — ties the OAuth callback back to the right
  employee, org, and connector without a server-side session.

**PKCE** (RFC 7636) is used for all OAuth flows unless the provider explicitly
does not support it. The ``code_verifier`` is baked into the signed state JWT
so it survives the browser redirect without server-side session storage.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.oauth import (
    decode_oauth_state,
    encode_oauth_state,
    frontend_redirect,
)
from app.core.security import decrypt_token, encrypt_token

if TYPE_CHECKING:
    from app.agent.tools.mcp.connectors.spec import ConnectorSpec
    from app.agent.tools.mcp.models import McpConnection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def _generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code verifier (RFC 7636).

    Returns a 128-character base64url-encoded string (no padding).
    """
    raw = os.urandom(96)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_code_challenge(verifier: str) -> str:
    """Compute the S256 PKCE code challenge for *verifier*."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# OAuth metadata discovery
# ---------------------------------------------------------------------------


async def _discover_oauth_metadata(spec: ConnectorSpec) -> dict:
    """Discover OAuth authorization server metadata for *spec*.

    Tries ``{token_url}/.well-known/oauth-authorization-server`` first,
    then falls back to the spec's configured URLs.

    Returns a dict with ``authorization_endpoint``, ``token_endpoint``,
    ``scopes_supported`` (optional), and ``code_challenge_methods_supported``
    (optional). Falls back to the spec's configured values on any failure.
    """
    base = spec.token_url or ""
    if base:
        discovery_url = base.rstrip("/oauth/token").rstrip("/token").rstrip("/")
        discovery_url += "/.well-known/oauth-authorization-server"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(discovery_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    meta: dict = {}
                    if "authorization_endpoint" in data:
                        meta["authorization_endpoint"] = data["authorization_endpoint"]
                    if "token_endpoint" in data:
                        meta["token_endpoint"] = data["token_endpoint"]
                    if "scopes_supported" in data:
                        meta["scopes_supported"] = data["scopes_supported"]
                    if "code_challenge_methods_supported" in data:
                        meta["code_challenge_methods_supported"] = data["code_challenge_methods_supported"]
                    return meta
        except Exception:
            logger.debug("OAuth metadata discovery failed for %s", spec.slug)

    return {}


# ---------------------------------------------------------------------------
# Signed state helpers
# ---------------------------------------------------------------------------


def _encode_oauth_state(
    employee_id: UUID,
    org_id: UUID,
    connector_slug: str,
    redirect_to: str | None = None,
    code_verifier: str | None = None,
    override_token_url: str | None = None,
    override_client_secret: str | None = None,
    override_client_id: str | None = None,
) -> str:
    """Create a short-lived signed token for the OAuth ``state`` parameter."""
    extra: dict[str, str] = {"connector_slug": connector_slug}
    if code_verifier:
        extra["code_verifier"] = code_verifier
    if override_token_url:
        extra["token_url"] = override_token_url
    if override_client_secret:
        extra["client_secret"] = override_client_secret
    if override_client_id:
        extra["client_id_override"] = override_client_id
    return encode_oauth_state(
        "mcp-oauth-state",
        employee_id=employee_id,
        org_id=org_id,
        extra_fields=extra,
        redirect_to=redirect_to,
    )


def _decode_oauth_state(state: str) -> dict | None:
    """Decode and validate the OAuth state token."""
    payload = decode_oauth_state(
        "mcp-oauth-state",
        state,
        required_fields={"employee_id", "org_id", "connector_slug"},
    )
    if payload is None:
        logger.warning("MCP OAuth state token is invalid or expired")
    return payload


# ---------------------------------------------------------------------------
# Public OAuth helpers
# ---------------------------------------------------------------------------


def build_authorize_url(
    spec: ConnectorSpec,
    employee_id: UUID,
    org_id: UUID,
    redirect_to: str | None = None,
    override_authorize_url: str | None = None,
    override_token_url: str | None = None,
    override_client_id: str | None = None,
    override_client_secret: str | None = None,
) -> str:
    """Build the full OAuth2 authorize URL for *spec* with JWT-encoded state
    and PKCE code challenge.

    Raises :class:`ValueError` when the connector spec or server settings
    are incomplete (missing ``authorize_url``, unconfigured client id,
    missing redirect URI).
    """
    effective_authorize = override_authorize_url or spec.authorize_url
    if not effective_authorize:
        raise ValueError(f"Connector '{spec.slug}' has no authorize_url configured.")

    # Resolve client_id: try override, then settings, then fail
    client_id_val = override_client_id
    client_secret_val = override_client_secret
    if not client_id_val:
        creds = settings.mcp_oauth_credentials.get(spec.slug)
        if creds and creds["client_id"]:
            client_id_val = creds["client_id"]
            client_secret_val = creds.get("client_secret", "")

    if not client_id_val:
        raise ValueError(
            f"OAuth client_id for '{spec.slug}' is not configured. "
            f"Set {spec.slug.upper()}_CLIENT_ID in the environment "
            "or pass client_id as a query parameter."
        )

    if not settings.mcp_oauth_redirect_uri:
        raise ValueError("MCP_OAUTH_REDIRECT_URI is not configured.")

    # PKCE: generate verifier, bake into state JWT, send challenge
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    state = _encode_oauth_state(
        employee_id, org_id, spec.slug, redirect_to, code_verifier,
        override_token_url=override_token_url,
        override_client_secret=client_secret_val if override_client_id else None,
        override_client_id=override_client_id,
    )

    params: dict[str, str] = {
        "client_id": client_id_val,
        "state": state,
        "redirect_uri": settings.mcp_oauth_redirect_uri,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    scope = " ".join(spec.default_scopes) if spec.default_scopes else ""
    if scope:
        params["scope"] = scope

    return f"{effective_authorize}?{urlencode(params)}"


async def exchange_code(
    spec: ConnectorSpec,
    code: str,
    code_verifier: str | None = None,
    override_token_url: str | None = None,
    override_client_id: str | None = None,
    override_client_secret: str | None = None,
) -> dict:
    """Exchange a temporary OAuth2 authorization ``code`` for tokens.

    If a ``code_verifier`` is provided (PKCE), it is included in the
    token request.  Otherwise falls back to the standard client_secret
    flow.

    ``override_*`` parameters let catalog-only OAuth connectors (figma, jira,
    etc.) participate in the flow by providing credentials at install time
    rather than having them hardcoded in the env.

    Returns the full token-response dict (``access_token``,
    ``refresh_token``, ``expires_in``, ``scope``, …).

    Raises :class:`ValueError` on configuration problems or missing fields
    in the response; raises :class:`httpx.HTTPError` on transport / HTTP
    errors.
    """
    effective_token_url = override_token_url or spec.token_url
    if not effective_token_url:
        raise ValueError(f"Connector '{spec.slug}' has no token_url configured.")

    # Resolve client_id / client_secret
    client_id_val = override_client_id
    client_secret_val = override_client_secret
    if not client_id_val:
        creds = settings.mcp_oauth_credentials.get(spec.slug)
        if creds and creds["client_id"]:
            client_id_val = creds["client_id"]
            client_secret_val = creds.get("client_secret", "")
    if not client_id_val:
        raise ValueError(
            f"OAuth credentials for '{spec.slug}' are not configured."
        )

    if not settings.mcp_oauth_redirect_uri:
        raise ValueError("MCP_OAUTH_REDIRECT_URI is not configured.")

    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.mcp_oauth_redirect_uri,
    }

    headers: dict[str, str] = {"Accept": "application/json"}

    if code_verifier:
        payload["code_verifier"] = code_verifier
        payload["client_id"] = client_id_val
    elif spec.token_auth_method == "basic":
        raw = f"{client_id_val}:{client_secret_val or ''}"
        headers["Authorization"] = f"Basic {base64.b64encode(raw.encode()).decode()}"
    else:
        payload["client_id"] = client_id_val
        payload["client_secret"] = client_secret_val or ""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            effective_token_url,
            data=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    if "access_token" not in data:
        raise ValueError(
            f"Token response from '{spec.slug}' missing access_token: "
            f"keys={list(data.keys())}"
        )

    return data


async def refresh_access_token(
    spec: ConnectorSpec,
    connection: McpConnection,
) -> str | None:
    """Attempt to refresh an expired OAuth2 access token using a stored
    refresh token.

    On success the *connection* record is updated in-place (caller must
    still commit the DB session).  Returns the new access-token string,
    or ``None`` if refresh is not possible (no refresh token stored,
    connector doesn't support refresh, or the provider rejected the
    attempt).
    """
    if not connection.oauth_refresh_token_enc:
        logger.debug("No refresh token stored for connection %s", connection.id)
        return None

    if not spec.token_url:
        logger.warning("Connector '%s' has no token_url for refresh", spec.slug)
        return None

    creds = settings.mcp_oauth_credentials.get(spec.slug)
    if not creds:
        logger.warning("No OAuth credentials configured for '%s'", spec.slug)
        return None

    refresh_token = decrypt_token(connection.oauth_refresh_token_enc)

    refresh_payload: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    refresh_headers: dict[str, str] = {"Accept": "application/json"}

    if spec.token_auth_method == "basic":
        raw = f"{creds['client_id']}:{creds['client_secret']}"
        refresh_headers["Authorization"] = f"Basic {base64.b64encode(raw.encode()).decode()}"
    else:
        refresh_payload["client_id"] = creds["client_id"]
        refresh_payload["client_secret"] = creds["client_secret"]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                spec.token_url,
                data=refresh_payload,
                headers=refresh_headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Token refresh failed for connection %s", connection.id)
        return None

    new_access_token: str | None = data.get("access_token")
    if not new_access_token:
        logger.warning(
            "Refresh response missing access_token for connection %s",
            connection.id,
        )
        return None

    # Rotate the stored secrets
    connection.credentials_enc = encrypt_token(new_access_token)
    if "refresh_token" in data:
        connection.oauth_refresh_token_enc = encrypt_token(data["refresh_token"])

    logger.info(
        "Refreshed OAuth token for connection %s (%s)", connection.id, spec.slug
    )
    return new_access_token


# ---------------------------------------------------------------------------
# Frontend redirect helper
# ---------------------------------------------------------------------------


def _frontend_redirect(
    employee_id: str,
    connector_slug: str,
    success: bool,
    detail: str = "",
    redirect_to: str | None = None,
) -> RedirectResponse:
    """Build a ``303 See Other`` redirect back to the frontend with
    ``mcp_oauth`` query parameters."""
    return frontend_redirect(
        employee_id,
        success,
        param_name="mcp_oauth",
        detail=detail,
        redirect_to=redirect_to,
        extra_params={"connector": connector_slug},
    )
