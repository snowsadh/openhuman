"""Focused tests for the lightweight ArmorIQ-governed Zop runtime."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app import zop_armoriq


class ZopArmorIQTests(IsolatedAsyncioTestCase):
    async def test_mcp_lists_only_the_governed_generation_tool(self) -> None:
        response = await zop_armoriq._handle_mcp_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )

        tools = response["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["generate_response"])

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
        client = Mock()
        client.invoke_with_policy.return_value = SimpleNamespace(
            result={
                "content": [
                    {"type": "text", "text": json.dumps({"response": "GOVERNED_OK"})}
                ]
            }
        )

        with (
            patch(
                "app.zop_armoriq.ensure_openhuman_mcp_registered",
                new=AsyncMock(),
            ),
            patch("app.zop_armoriq.mint_intent_token", return_value=token) as mint,
            patch("app.zop_armoriq.get_armoriq_client", return_value=client),
        ):
            response, plan_hash = await zop_armoriq.generate_response_through_armoriq(
                content="Verify governance",
                system_prompt="Reply exactly",
                employee_id="employee-1",
                user_email="owner@example.com",
            )

        self.assertEqual(response, "GOVERNED_OK")
        self.assertEqual(plan_hash, "signed-plan")
        mint.assert_called_once()
        client.invoke_with_policy.assert_called_once()
