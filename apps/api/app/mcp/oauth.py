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
import re
from datetime import UTC, datetime, timedelta
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


async def discover_oauth_metadata(spec: ConnectorSpec) -> dict:
    """Resolve hosted-MCP OAuth metadata from trusted connector endpoints."""
    metadata: dict = {}
    if spec.authorize_url:
        metadata["authorization_endpoint"] = spec.authorize_url
    if spec.token_url:
        metadata["token_endpoint"] = spec.token_url
    if metadata.keys() >= {"authorization_endpoint", "token_endpoint"}:
        return metadata
    if not spec.base_url:
        return metadata

    base_url = spec.base_url.rstrip("/")
    protected_urls: list[str] = []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(base_url)
            challenge = response.headers.get("www-authenticate", "")
            match = re.search(r'resource_metadata="([^"]+)"', challenge)
            if match:
                protected_urls.append(match.group(1))

            parsed = httpx.URL(base_url)
            origin = f"{parsed.scheme}://{parsed.host}"
            if parsed.port:
                origin += f":{parsed.port}"
            protected_urls.extend(
                [
                    f"{origin}/.well-known/oauth-protected-resource{parsed.path.rstrip('/')}",
                    f"{base_url}/.well-known/oauth-protected-resource",
                    f"{origin}/.well-known/oauth-protected-resource",
                ]
            )

            authorization_servers: list[str] = []
            for url in dict.fromkeys(protected_urls):
                candidate = await client.get(url)
                if candidate.status_code != 200:
                    continue
                payload = candidate.json()
                authorization_servers.extend(payload.get("authorization_servers", []))
                for field in ("authorization_endpoint", "token_endpoint"):
                    if payload.get(field):
                        metadata[field] = payload[field]
                break

            for issuer in authorization_servers:
                issuer = issuer.rstrip("/")
                issuer_url = httpx.URL(issuer)
                issuer_origin = f"{issuer_url.scheme}://{issuer_url.host}"
                if issuer_url.port:
                    issuer_origin += f":{issuer_url.port}"
                well_known = [
                    f"{issuer_origin}/.well-known/oauth-authorization-server"
                    f"{issuer_url.path.rstrip('/')}",
                    f"{issuer}/.well-known/oauth-authorization-server",
                    f"{issuer_origin}/.well-known/openid-configuration",
                ]
                for url in dict.fromkeys(well_known):
                    candidate = await client.get(url)
                    if candidate.status_code != 200:
                        continue
                    payload = candidate.json()
                    for field in (
                        "authorization_endpoint",
                        "token_endpoint",
                        "scopes_supported",
                        "code_challenge_methods_supported",
                    ):
                        if payload.get(field):
                            metadata[field] = payload[field]
                    break
                if metadata.keys() >= {"authorization_endpoint", "token_endpoint"}:
                    break
    except Exception:
        logger.exception("OAuth metadata discovery failed for trusted MCP %s", spec.slug)
    return metadata


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
) -> str:
    """Create a short-lived signed token for the OAuth ``state`` parameter."""
    extra: dict[str, str] = {"connector_slug": connector_slug}
    if code_verifier:
        extra["code_verifier"] = code_verifier
    if override_token_url:
        extra["token_url"] = override_token_url
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

    creds = settings.mcp_oauth_credentials.get(spec.slug)
    client_id_val = creds["client_id"] if creds else ""

    if not client_id_val:
        raise ValueError(
            f"OAuth client_id for '{spec.slug}' is not configured. "
            f"Set {spec.slug.upper()}_CLIENT_ID in the environment "
            "in Secrets Manager."
        )

    if not settings.mcp_oauth_redirect_uri:
        raise ValueError("MCP_OAUTH_REDIRECT_URI is not configured.")

    # PKCE: generate verifier, bake into state JWT, send challenge
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    state = _encode_oauth_state(
        employee_id,
        org_id,
        spec.slug,
        redirect_to,
        code_verifier,
        override_token_url=override_token_url,
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
) -> dict:
    """Exchange a temporary OAuth2 authorization ``code`` for tokens.

    If a ``code_verifier`` is provided (PKCE), it is included in the
    token request.  Otherwise falls back to the standard client_secret
    flow.

    A discovered token URL may be provided for OAuth 2.1 hosted MCP servers.

    Returns the full token-response dict (``access_token``,
    ``refresh_token``, ``expires_in``, ``scope``, …).

    Raises :class:`ValueError` on configuration problems or missing fields
    in the response; raises :class:`httpx.HTTPError` on transport / HTTP
    errors.
    """
    effective_token_url = override_token_url or spec.token_url
    if not effective_token_url:
        raise ValueError(f"Connector '{spec.slug}' has no token_url configured.")

    creds = settings.mcp_oauth_credentials.get(spec.slug)
    client_id_val = creds["client_id"] if creds else ""
    client_secret_val = creds.get("client_secret", "") if creds else ""
    if not client_id_val:
        raise ValueError(f"OAuth credentials for '{spec.slug}' are not configured.")

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
    if spec.token_auth_method == "basic":
        raw = f"{client_id_val}:{client_secret_val or ''}"
        headers["Authorization"] = f"Basic {base64.b64encode(raw.encode()).decode()}"
    else:
        payload["client_id"] = client_id_val
        if client_secret_val:
            payload["client_secret"] = client_secret_val

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
            f"Token response from '{spec.slug}' missing access_token: keys={list(data.keys())}"
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

    token_url = connection.oauth_token_url or spec.token_url
    if not token_url:
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
                token_url,
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
    if expires_in := data.get("expires_in"):
        connection.oauth_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    logger.info("Refreshed OAuth token for connection %s (%s)", connection.id, spec.slug)
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
