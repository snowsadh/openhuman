from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from app.agent.tools.mcp.connectors.registry import REGISTRY
from app.core.config import settings
from app.mcp.adapters import zendesk_mcp
from app.mcp.credential_package import (
    pack_adapter_credential,
    unpack_adapter_credential,
)
from app.mcp.oauth import _decode_oauth_state, build_authorize_url


def test_adapter_credentials_are_opaque_and_typed() -> None:
    packed = pack_adapter_credential(
        "zendesk",
        account_url="https://example.zendesk.com",
        email="owner@example.com",
        api_token="secret-token",
    )

    assert packed.startswith("ohmcp1.")
    assert "secret-token" not in packed
    unpacked = unpack_adapter_credential(packed, "zendesk")
    assert unpacked["email"] == "owner@example.com"
    with pytest.raises(ValueError):
        unpack_adapter_credential(packed, "n8n")


@pytest.mark.asyncio
async def test_zendesk_adapter_advertises_only_narrow_tools() -> None:
    response = await zendesk_mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        None,
    )
    names = {tool["name"] for tool in response["result"]["tools"]}

    assert names == {
        "get_ticket",
        "search_tickets",
        "get_user",
        "search_help_center",
        "reply_to_ticket",
        "update_ticket_status",
    }
    assert "delete_user" not in names
    assert "issue_refund" not in names


def test_oauth_state_never_contains_client_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = REGISTRY["hubspot"]
    monkeypatch.setattr(settings, "hubspot_client_id", "public-client-id")
    monkeypatch.setattr(settings, "hubspot_client_secret", "server-only-secret")
    monkeypatch.setattr(
        settings,
        "mcp_oauth_redirect_uri",
        "https://example.com/api/mcp/oauth/callback",
    )

    authorization_url = build_authorize_url(
        spec,
        uuid4(),
        uuid4(),
        override_authorize_url="https://app.hubspot.com/oauth/authorize",
        override_token_url="https://api.hubapi.com/oauth/v3/token",
    )
    state = parse_qs(urlparse(authorization_url).query)["state"][0]
    payload = _decode_oauth_state(state)

    assert payload is not None
    assert payload["connector_slug"] == "hubspot"
    assert payload["token_url"] == "https://api.hubapi.com/oauth/v3/token"
    assert "code_verifier" in payload
    assert "client_secret" not in payload
    assert "server-only-secret" not in state
