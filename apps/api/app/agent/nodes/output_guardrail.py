from langchain_core.messages import AIMessage
import logging

from app.activity.service import record_activity_from_context
from app.agent.guardrails import check_output
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def output_guardrail_node(state: AgentState) -> dict:
    """Validate LLM-generated response against output guardrails.

    Reads the employee-specific guardrail config from state (set earlier by
    ``input_guardrail_node`` or ``build_prompt_node``) so template rules
    like citation requirements are enforced.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"output_guardrail_passed": True}

    # Find the last assistant message
    ai_msg = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)), None
    )
    if not ai_msg:
        return {"output_guardrail_passed": True}

    content = str(ai_msg.content)
    guardrail_config = state.get("guardrail_config", {})
    passed, reason = check_output(content, guardrail_config)

    if not passed:
        logger.warning(
            "[Output Guardrail Blocked] Response blocked. Reason: %s | Output: '%s...'",
            reason,
            content[:100],
        )
        await record_activity_from_context(
            "ai_engine",
            "Output guardrail blocked response",
            status="blocked",
            metadata={
                "stage": "output_guardrail",
                "reason": reason,
                "output_preview": content[:200],
            },
        )
        return {
            "output_guardrail_passed": False,
            "response": (
                "I apologize, but my response was blocked due to "
                "safety guidelines."
            ),
        }

    return {"output_guardrail_passed": True}
