"""Small shared ArmorIQ boundary for MCP-backed agent tools."""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

from armoriq_sdk import ArmorIQClient

from app.core.config import settings

_token_lock = threading.Lock()

_ROLE_AGENT_IDS = {
    "hr": "openhuman-hr",
    "sales": "openhuman-sales",
    "support": "openhuman-support",
    "legal-compliance": "openhuman-legal",
    "legal_compliance": "openhuman-legal",
    "legal": "openhuman-legal",
}


def agent_id_for_employee_kind(employee_kind: str | None) -> str:
    """Return the stable ArmorIQ agent identity for an employee role."""
    normalized = (employee_kind or "").strip().lower().replace(" ", "_")
    return _ROLE_AGENT_IDS.get(normalized, "openhuman")


def parse_mcp_tool_name(tool_name: str) -> tuple[str, str] | None:
    """Map ``mcp__server__action`` to ArmorIQ's MCP/action pair."""
    parts = tool_name.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


@lru_cache(maxsize=8)
def get_armoriq_client(agent_id: str = "openhuman") -> ArmorIQClient:
    """Create the SDK client lazily so non-MCP runs need no ArmorIQ key."""
    return ArmorIQClient(
        api_key=settings.armoriq_api_key,
        agent_id=agent_id,
        timeout=float(settings.armoriq_request_timeout_seconds),
    )


def get_request_armoriq_client(
    *,
    agent_id: str,
    mcp: str,
    credentials: str | None,
    auth_type: str | None = None,
) -> ArmorIQClient:
    """Create a request-scoped client containing only one MCP credential.

    The process-level client remains responsible for plan capture. Credentialed
    execution clients are deliberately not cached so one organization or user
    can never inherit another connection's token mapping.
    """
    if not credentials:
        return get_armoriq_client(agent_id=agent_id)
    credential_mapping: dict[str, str]
    if auth_type in {"api_key", "api_key_header"}:
        credential_mapping = {"authType": "api_key", "apiKey": credentials}
    else:
        credential_mapping = {"authType": "bearer", "token": credentials}
    return ArmorIQClient(
        api_key=settings.armoriq_api_key,
        agent_id=agent_id,
        timeout=float(settings.armoriq_request_timeout_seconds),
        mcp_credentials={mcp: credential_mapping},
    )


def mint_intent_token(
    *,
    prompt: str,
    steps: list[dict[str, Any]],
    user_email: str | None,
    metadata: dict[str, Any],
) -> Any:
    """Capture a plan and mint its token with request-safe user attribution."""
    client = get_armoriq_client()
    with _token_lock:
        previous_email = client.user_email_override
        client.user_email_override = user_email.strip().lower() if user_email else None
        try:
            capture = client.capture_plan(
                llm=settings.openai_model,
                prompt=prompt,
                plan={"goal": prompt, "steps": steps},
                metadata=metadata,
            )
            return client.get_intent_token(
                capture,
                validity_seconds=settings.armoriq_approval_timeout_seconds + 60,
            )
        finally:
            client.user_email_override = previous_email
