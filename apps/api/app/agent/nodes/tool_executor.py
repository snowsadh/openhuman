import json
import logging
from uuid import UUID

from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)


class CustomToolNode(ToolNode):
    """A ToolNode subclass that increments tool_round, logs executions, and records per-tool activity."""

    async def ainvoke(self, input, config=None, **kwargs):  # type: ignore[no-untyped-def]
        current_round = input.get("tool_round", 0)
        logger.info("[Tool Node] Executing tools round %d", current_round)

        # Execute tools using base implementation
        result = await super().ainvoke(input, config, **kwargs)

        # Log outputs
        if isinstance(result, dict):
            for message in result.get("messages", []):
                tool_name = getattr(message, "name", "unknown")
                content = getattr(message, "content", "")
                logger.info(
                    "[Tool Executed] Tool: %s | Output Snippet: '%s...'",
                    tool_name,
                    str(content)[:150],
                )

        # Increment tool round in state
        result["tool_round"] = current_round + 1

        # ── Record per-tool activity (best-effort) ─────────────────────────
        await self._record_tool_activity(input, result)

        return result

    async def _record_tool_activity(
        self, input: dict, result: dict
    ) -> None:  # type: ignore[no-untyped-def]
        """Record each tool call as an activity event."""
        try:
            from app.activity.context import (
                activity_channel_id,
                activity_employee_id,
                activity_employee_name,
                activity_org_id,
                activity_platform,
            )
            from app.activity.service import record_activity
            from app.core.database import async_session_factory

            org_id = activity_org_id.get()
            emp_id = activity_employee_id.get()
            emp_name = activity_employee_name.get()
            platform = activity_platform.get()
            channel_id = activity_channel_id.get()

            if not org_id or not emp_id:
                return

            # Extract tool calls from the input messages
            messages = input.get("messages", [])
            result_messages = result.get("messages", [])

            for i, msg in enumerate(messages):
                if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                    continue

                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})

                    # Find matching tool result
                    tool_result = None
                    tool_error = None
                    for rm in result_messages:
                        if (
                            hasattr(rm, "tool_call_id")
                            and rm.tool_call_id == tc.get("id")
                        ):
                            tool_result = getattr(rm, "content", None)
                            if hasattr(rm, "status") and rm.status == "error":
                                tool_error = tool_result
                            break

                    desc_parts = {"tool": tool_name, "args": tool_args}
                    if tool_result is not None and not tool_error:
                        result_str = str(tool_result)
                        desc_parts["result"] = result_str[:300]

                    try:
                        async with async_session_factory() as s:
                            await record_activity(
                                s,
                                UUID(org_id),
                                "tool_usage",
                                f"Tool: {tool_name}{' (failed)' if tool_error else ''}",
                                employee_id=UUID(emp_id),
                                employee_name=emp_name,
                                platform=platform,
                                status="failed" if tool_error else "succeeded",
                                description=json.dumps(desc_parts),
                                metadata={
                                    "tool_name": tool_name,
                                    "channel_id": channel_id,
                                    "error": str(tool_error)[:200] if tool_error else None,
                                },
                            )
                    except Exception:
                        logger.debug(
                            "Failed to record tool activity for %s", tool_name, exc_info=True,
                        )

        except Exception:
            logger.debug("Failed to record tool activity batch", exc_info=True)
