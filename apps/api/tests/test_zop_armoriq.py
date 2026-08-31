"""Focused tests for the lightweight ArmorIQ-governed Zop runtime."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app import zop_armoriq


class ZopArmorIQTests(IsolatedAsyncioTestCase):
    async def test_general_mcp_lists_only_the_governed_generation_tool(self) -> None:
        response = await zop_armoriq._handle_mcp_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )

        tools = response["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["generate_response"])

    async def test_role_mcps_expose_safe_and_approval_tools(self) -> None:
        expected = {
            zop_armoriq.HR_MCP_SLUG: ["answer_hr_question", "prepare_pto_request"],
            zop_armoriq.SALES_MCP_SLUG: [
                "draft_sales_response",
                "prepare_discount_request",
            ],
            zop_armoriq.SUPPORT_MCP_SLUG: [
                "draft_support_response",
                "prepare_refund_request",
            ],
            zop_armoriq.LEGAL_MCP_SLUG: [
                "review_legal_question",
                "prepare_legal_document_share",
            ],
        }
        for server_slug, tool_names in expected.items():
            response = await zop_armoriq._handle_mcp_request(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                server_slug,
            )
            self.assertEqual(
                [tool["name"] for tool in response["result"]["tools"]],
                tool_names,
            )

    async def test_status_reports_role_servers_and_default_deny(self) -> None:
        with patch(
            "app.zop_armoriq.ensure_armoriq_runtime_ready",
            new=AsyncMock(),
        ):
            response = await zop_armoriq.armoriq_status()

        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["default_action"], "block")
        self.assertEqual(
            {server["slug"] for server in response["servers"]},
            {
                zop_armoriq.MCP_SLUG,
                zop_armoriq.HR_MCP_SLUG,
                zop_armoriq.SALES_MCP_SLUG,
                zop_armoriq.SUPPORT_MCP_SLUG,
                zop_armoriq.LEGAL_MCP_SLUG,
            },
        )

    async def test_mcp_tool_returns_json_string_content(self) -> None:
        with patch(
            "app.zop_armoriq._run_openai_action",
            new=AsyncMock(return_value={"response": "ARMORIQ_OK", "model": "test"}),
        ):
            response = await zop_armoriq._handle_mcp_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "generate_response",
                        "arguments": {
                            "content": "Verify",
                            "system_prompt": "Reply concisely",
                            "employee_id": "employee-1",
                        },
                    },
                }
            )

        text_payload = response["result"]["content"][0]["text"]
        self.assertEqual(json.loads(text_payload)["response"], "ARMORIQ_OK")

    async def test_generation_uses_signed_token_and_armoriq_invoke(self) -> None:
        token = SimpleNamespace(plan_hash="signed-plan")
        session = Mock()
        session.start_plan.return_value = token
        session.check.return_value = SimpleNamespace(allowed=True, action="allow", reason=None)
        session.dispatch.return_value = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "response": "GOVERNED_OK",
                            "model": "test-model",
                            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                        }
                    ),
                }
            ]
        }
        scope = Mock()
        scope.start_session.return_value = session
        client = Mock()
        client.for_user.return_value = scope

        with (
            patch(
                "app.zop_armoriq.ensure_armoriq_runtime_ready",
                new=AsyncMock(),
            ),
            patch("app.zop_armoriq.get_armoriq_client", return_value=client) as client_factory,
        ):
            (
                response,
                plan_hash,
                mcp_slug,
                action,
            ) = await zop_armoriq.generate_response_through_armoriq(
                content="Verify governance",
                system_prompt="Reply exactly",
                employee_id="employee-1",
                user_email="owner@example.com",
                employee_kind="hr",
            )

        self.assertEqual(response, "GOVERNED_OK")
        self.assertEqual(plan_hash, "signed-plan")
        self.assertEqual(mcp_slug, zop_armoriq.HR_MCP_SLUG)
        self.assertEqual(action, zop_armoriq.HR_RESPONSE_ACTION)
        client_factory.assert_called_once_with(agent_id="openhuman-hr")
        session.start_plan.assert_called_once()
        session.check.assert_called_once()
        session.dispatch.assert_called_once()
        session.record_generation.assert_called_once()
        session.flush_observability.assert_called_once()
        session.close.assert_called_once()

    async def test_approval_tool_is_side_effect_free(self) -> None:
        response = await zop_armoriq._handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": zop_armoriq.HR_APPROVAL_ACTION,
                    "arguments": {
                        "employee_name": "Sam",
                        "start_date": "2026-09-01",
                        "end_date": "2026-09-02",
                        "reason": "Family appointment",
                    },
                },
            },
            zop_armoriq.HR_MCP_SLUG,
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "prepared_for_human_approval")
        self.assertFalse(payload["side_effect_performed"])
