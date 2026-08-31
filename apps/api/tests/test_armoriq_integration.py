"""Focused proof that the shared MCP boundary cannot bypass ArmorIQ."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from armoriq_sdk.exceptions import PolicyBlockedException, PolicyHoldException
from armoriq_sdk.models import HoldInfo, IntentToken
from langchain_core.tools import StructuredTool

from app.agent.armoriq import get_request_armoriq_client
from app.agent.tools.mcp.client import MCPClientManager, _get_circuit_breaker


def _token() -> IntentToken:
    now = time.time()
    plan = {
        "steps": [
            {
                "mcp": "identity-test",
                "action": "assign_group",
                "params": {"user": "sam", "group": "engineering"},
            }
        ]
    }
    return IntentToken(
        token_id="test-token",
        plan_hash="test-plan-hash",
        signature="test-signature",
        issued_at=now,
        expires_at=now + 600,
        composite_identity="test-identity",
        raw_token={"plan": plan},
        step_proofs=[[{"test": "proof"}]],
        total_steps=1,
    )


def _tool(calls: list[dict]) -> StructuredTool:
    async def original(user: str, group: str) -> str:
        calls.append({"user": user, "group": group})
        return "original MCP adapter ran"

    return StructuredTool.from_function(
        coroutine=original,
        name="mcp__identity-test__assign_group",
        description="Assign a user to an identity group",
    )


async def _run_inline(function, *args):  # type: ignore[no-untyped-def]
    """Keep this unit test independent of asyncio's process-wide thread pool."""
    return function(*args)


def test_request_client_contains_only_selected_mcp_credential() -> None:
    with patch("app.agent.armoriq.ArmorIQClient") as constructor:
        get_request_armoriq_client(
            agent_id="openhuman-sales",
            mcp="hubspot",
            credentials="oauth-token",
            auth_type="oauth2",
        )

    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["agent_id"] == "openhuman-sales"
    assert kwargs["mcp_credentials"] == {
        "hubspot": {"authType": "bearer", "token": "oauth-token"}
    }


@pytest.mark.asyncio
async def test_allowed_call_executes_once_through_armoriq() -> None:
    original_calls: list[dict] = []
    tool = MCPClientManager()._wrap_tool(_tool(original_calls), "identity-test", None)
    client = Mock()
    client.invoke_with_policy.return_value = SimpleNamespace(result="ArmorIQ executed it")

    with (
        patch(
            "app.agent.tools.mcp.client.get_request_armoriq_client",
            return_value=client,
        ),
        patch(
            "app.agent.tools.mcp.client.record_activity_from_context",
            new=AsyncMock(),
        ),
        patch("app.agent.tools.mcp.client.asyncio.to_thread", side_effect=_run_inline),
    ):
        result = await tool.ainvoke(
            {"user": "sam", "group": "engineering"},
            config={
                "configurable": {
                    "armoriq_intent_token": _token().model_dump(mode="json"),
                    "armoriq_user_email": "admin@example.com",
                }
            },
        )

    assert result == "ArmorIQ executed it"
    assert client.invoke_with_policy.call_count == 1
    assert original_calls == []


@pytest.mark.asyncio
async def test_hold_is_persisted_before_approved_action_executes() -> None:
    tool = MCPClientManager()._wrap_tool(_tool([]), "identity-test", None)
    client = Mock()

    def invoke_with_hold(_mcp, _action, _token_value, _params, options):
        options.on_hold(
            HoldInfo(
                delegation_id="delegation-42",
                reason="Human approval required",
                tool="assign_group",
                mcp="identity-test",
            )
        )
        return SimpleNamespace(result={"status": "assigned"})

    client.invoke_with_policy.side_effect = invoke_with_hold
    persist = AsyncMock()
    update = AsyncMock()

    with (
        patch(
            "app.agent.tools.mcp.client.get_request_armoriq_client",
            return_value=client,
        ),
        patch(
            "app.agent.tools.mcp.client.persist_hold_from_context",
            new=persist,
        ),
        patch(
            "app.agent.tools.mcp.client.update_approval_execution_from_context",
            new=update,
        ),
        patch(
            "app.agent.tools.mcp.client.record_activity_from_context",
            new=AsyncMock(),
        ),
    ):
        result = await tool.ainvoke(
            {"user": "sam", "group": "engineering"},
            config={
                "configurable": {
                    "armoriq_intent_token": _token().model_dump(mode="json"),
                    "armoriq_user_email": "admin@example.com",
                }
            },
        )

    assert result == {"status": "assigned"}
    persist.assert_awaited_once()
    update.assert_awaited_once_with(
        plan_hash="test-plan-hash",
        mcp="identity-test",
        action="assign_group",
        status="executed",
        result={"status": "assigned"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enforcement_error",
    [
        PolicyBlockedException(
            "finance-admin is blocked",
            enforcement_action="block",
            reason="privileged_role",
        ),
        PolicyHoldException("finance-admin requires approval"),
    ],
)
async def test_held_or_blocked_call_never_reaches_original_mcp(
    enforcement_error: Exception,
) -> None:
    original_calls: list[dict] = []
    tool = MCPClientManager()._wrap_tool(_tool(original_calls), "identity-test-block", None)
    client = Mock()
    client.invoke_with_policy.side_effect = enforcement_error
    circuit = _get_circuit_breaker("identity-test-block")
    failures_before = circuit.failure_count

    with (
        patch(
            "app.agent.tools.mcp.client.get_request_armoriq_client",
            return_value=client,
        ),
        patch(
            "app.agent.tools.mcp.client.record_activity_from_context",
            new=AsyncMock(),
        ),
        patch("app.agent.tools.mcp.client.asyncio.to_thread", side_effect=_run_inline),
    ):
        with pytest.raises(type(enforcement_error)):
            await tool.ainvoke(
                {"user": "sam", "group": "finance-admin"},
                config={
                    "configurable": {
                        "armoriq_intent_token": _token().model_dump(mode="json"),
                        "armoriq_user_email": "admin@example.com",
                    }
                },
            )

    assert original_calls == []
    assert circuit.failure_count == failures_before
