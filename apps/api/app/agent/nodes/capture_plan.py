"""Capture the model's pending MCP actions before any tool can execute."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.activity.service import record_activity_from_context
from app.agent.armoriq import mint_intent_token, parse_mcp_tool_name
from app.agent.state import AgentState


async def capture_plan_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage):
        return {"armoriq_intent_token": None}

    steps: list[dict[str, Any]] = []
    for call in last.tool_calls:
        parsed = parse_mcp_tool_name(call.get("name", ""))
        if parsed is None:
            continue
        mcp, action = parsed
        steps.append(
            {
                "mcp": mcp,
                "action": action,
                "tool": action,
                "params": call.get("args", {}),
                "description": f"Call {action} on {mcp}",
            }
        )

    if not steps:
        return {"armoriq_intent_token": None}

    prompt = next(
        (
            str(message.content)
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
        ),
        "OpenHuman agent task",
    )
    configurable = config.get("configurable", {})
    try:
        token = await asyncio.to_thread(
            mint_intent_token,
            prompt=prompt,
            steps=steps,
            user_email=configurable.get("armoriq_user_email"),
            metadata={
                "employee_id": configurable.get("employee_id"),
                "platform": configurable.get("platform"),
            },
        )
    except Exception as exc:
        await record_activity_from_context(
            "armoriq_blocked",
            "ArmorIQ rejected plan capture",
            status="blocked",
            metadata={"reason": str(exc)[:300]},
        )
        raise

    await record_activity_from_context(
        "armoriq_plan",
        f"ArmorIQ captured a {len(steps)}-step MCP plan",
        status="succeeded",
        description=json.dumps(
            {"steps": [{"mcp": step["mcp"], "action": step["action"]} for step in steps]}
        ),
        metadata={"plan_hash": token.plan_hash, "step_count": len(steps)},
    )
    return {"armoriq_intent_token": token.model_dump(mode="json")}
