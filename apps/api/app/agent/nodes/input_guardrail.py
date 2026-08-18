from uuid import UUID
import logging

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.guardrails import check_input
from app.agent.state import AgentState
from app.activity.service import record_activity_from_context
from app.employees.models import Employee
from app.employees.templates import get_employee_template

logger = logging.getLogger(__name__)


async def _load_guardrail_config(
    config: RunnableConfig,
) -> dict:
    """Load the guardrail config for the employee referenced in *config*.

    Returns an empty dict when no DB / employee is available so the
    guardrails use their safe defaults.
    """
    configurable = config.get("configurable", {})
    db: AsyncSession | None = configurable.get("db")
    employee_id_str = configurable.get("employee_id")

    if not db or not employee_id_str:
        return {}

    try:
        emp = await db.scalar(
            select(Employee).where(Employee.id == UUID(employee_id_str))
        )
        if emp is None:
            return {}
        template = get_employee_template(emp)
        return template.guardrail_config
    except (ValueError, AttributeError):
        return {}


async def input_guardrail_node(
    state: AgentState, config: RunnableConfig
) -> dict:
    """Validate incoming user message against input guardrails.

    Loads the employee-specific guardrail config from the database so that
    template rules (e.g. ``block_pii``, ``require_citations``) are actually
    enforced.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"input_blocked": False, "block_reason": None}

    # Find the last human message
    user_msg = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    if not user_msg:
        return {"input_blocked": False, "block_reason": None}

    # Load guardrail config from employee template
    guardrail_config = await _load_guardrail_config(config)

    # Perform guardrail check with the template config
    content = str(user_msg.content)
    is_blocked, reason = check_input(content, guardrail_config)

    if is_blocked:
        logger.warning(
            "[Input Guardrail Blocked] Employee ID: %s | Reason: %s | Input: '%s...'",
            config.get("configurable", {}).get("employee_id"),
            reason,
            content[:100],
        )
        await record_activity_from_context(
            "ai_engine",
            "Input guardrail blocked request",
            status="blocked",
            metadata={
                "stage": "input_guardrail",
                "reason": reason,
                "input_preview": content[:200],
            },
        )
        return {
            "input_blocked": True,
            "block_reason": reason,
            "guardrail_config": guardrail_config,
            "response": (
                "I cannot process this request due to safety policy: "
                + (reason or "")
            ),
        }

    return {
        "input_blocked": False,
        "block_reason": None,
        "guardrail_config": guardrail_config,
    }
