from __future__ import annotations

from urllib.parse import quote_plus
from uuid import UUID

from fastapi.responses import RedirectResponse
from itsdangerous import BadData, URLSafeTimedSerializer

from app.core.config import settings

STATE_MAX_AGE = 600  # 10 minutes


def get_state_secret() -> str:
    """Return a secret key for signing OAuth state tokens."""
    return settings.encryption_key or settings.jwt_secret_key or "change-me"


def _get_serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_state_secret(), salt=salt)


def encode_oauth_state(
    salt: str,
    *,
    employee_id: UUID,
    org_id: UUID,
    extra_fields: dict[str, str] | None = None,
    redirect_to: str | None = None,
) -> str:
    """Create a short-lived signed token for the OAuth ``state`` parameter.

    Parameters
    ----------
    salt:
        Serializer salt — must match between encode and decode.
    employee_id, org_id:
        Identifiers baked into the state so the callback can recover them.
    extra_fields:
        Additional key-value pairs to include in the payload
        (e.g. ``connector_slug`` for MCP flows).
    redirect_to:
        Optional URL to redirect the browser to after the flow completes.
    """
    payload: dict[str, str] = {
        "employee_id": str(employee_id),
        "org_id": str(org_id),
    }
    if extra_fields:
        payload.update(extra_fields)
    if redirect_to:
        payload["redirect_to"] = redirect_to
    return _get_serializer(salt).dumps(payload)


def decode_oauth_state(
    salt: str,
    state: str,
    *,
    required_fields: set[str] | None = None,
) -> dict | None:
    """Decode and validate an OAuth state token.

    Returns the payload dict or ``None`` if the token is expired, tampered
    with, or has missing fields.
    """
    try:
        payload = _get_serializer(salt).loads(state, max_age=STATE_MAX_AGE)
    except BadData:
        return None

    if not isinstance(payload, dict):
        return None

    if required_fields and not required_fields.issubset(payload.keys()):
        return None

    return payload


def frontend_redirect(
    employee_id: str,
    success: bool,
    param_name: str,
    *,
    detail: str = "",
    redirect_to: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> RedirectResponse:
    """Build a ``303 See Other`` redirect back to the frontend.

    Parameters
    ----------
    employee_id:
        Employee UUID to include in the query string.
    success:
        ``True`` → ``{param_name}=connected``, ``False`` → ``{param_name}=error``.
    param_name:
        Query parameter name for the status (e.g. ``"slack"`` or ``"mcp_oauth"``).
    detail:
        Error detail appended as ``?reason=...`` when ``success=False``.
    redirect_to:
        Override the base redirect URL; defaults to ``settings.frontend_url``.
    extra_params:
        Additional query parameters to append
        (e.g. ``{"connector": connector_slug}``).
    """
    base_url = redirect_to or settings.frontend_url
    separator = "&" if "?" in base_url else "?"
    status_str = "connected" if success else "error"
    url = f"{base_url.rstrip('/')}{separator}{param_name}={status_str}"
    if extra_params:
        for k, v in extra_params.items():
            url += f"&{k}={quote_plus(v)}"
    if not success:
        url += f"&reason={quote_plus(detail)}"
    url += f"&employee_id={quote_plus(employee_id)}"
    return RedirectResponse(url, status_code=303)
