from uuid import UUID
import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity_from_context
from app.agent.llm import get_llm
from app.agent.state import AgentState
from app.employees.models import Employee
from app.employees.templates import get_employee_template

logger = logging.getLogger(__name__)


async def llm_call_node(state: AgentState, config: RunnableConfig) -> dict:
    """Invoke LLM on current messages, binding only the tools allowed for
    this employee.

    The full tool set (built-in + MCP) is passed via ``configurable.all_tools``.
    This node filters down to the employee-template subset:

    * Built-in tools — gated by ``EmployeeTemplate.allowed_tools``.
    * MCP tools      — gated by ``EmployeeTemplate.allowed_mcp_servers``
      (each MCP tool is prefixed ``mcp__{slug}__``).

    If the employee / template specifies no tools the LLM is called without
    any bound tools — there is NO implicit fallback to the full set.
    """
    configurable = config.get("configurable", {})
    db: AsyncSession | None = configurable.get("db")
    employee_id_str = configurable.get("employee_id")

    # The full tool set (built-in + MCP) passed from the router
    all_tools: list[BaseTool] = configurable.get("all_tools", [])

    # Determine allowed tools for this specific employee
    allowed_tools: list[BaseTool] = []
    if db and employee_id_str:
        emp = await db.scalar(
            select(Employee).where(Employee.id == UUID(employee_id_str))
        )
        if emp:
            template = get_employee_template(emp)

            # -- built-in tools: exact name match against allowed_tools -----
            allowed_builtin_names = set(template.allowed_tools)
            allowed_builtin = [
                t for t in all_tools
                if not _is_mcp_tool(t) and t.name in allowed_builtin_names
            ]

            # -- MCP tools: match by server slug prefix --------------------
            allowed_servers = set(template.allowed_mcp_servers)
            if "*" in allowed_servers:
                allowed_mcp = [t for t in all_tools if _is_mcp_tool(t)]
            elif allowed_servers:
                allowed_mcp = [
                    t for t in all_tools
                    if _is_mcp_tool(t) and _mcp_slug(t) in allowed_servers
                ]
            else:
                allowed_mcp = []

            allowed_tools = allowed_builtin + allowed_mcp

    # Initialise LLM — when allowed_tools is empty the model runs with no
    # bound tools, which is the correct behaviour for a restricted employee.
    llm = get_llm(tools=allowed_tools)

    logger.info(
        "[LLM Node] Invoking LLM for employee: %s | Bound Tools Count: %d | Tools: %s",
        employee_id_str,
        len(allowed_tools),
        [t.name for t in allowed_tools],
    )
    await record_activity_from_context(
        "ai_engine",
        "LLM invoked",
        status="running",
        metadata={
            "stage": "llm_call",
            "bound_tools_count": len(allowed_tools),
            "tools": [t.name for t in allowed_tools],
        },
    )

    # Call LLM
    # System instructions are a stable prefix, not persisted conversation
    # messages. Filter legacy stored SystemMessages before prepending one
    # canonical prompt for this call.
    conversation = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
    llm_messages = [SystemMessage(content=state.get("system_prompt", "")), *conversation]
    response = await llm.ainvoke(llm_messages, config=config)

    # Extract raw text (may be empty when the response contains only
    # tool_calls)
    raw_text = ""
    if isinstance(response, AIMessage):
        content = response.content
        raw_text = str(content) if content else ""

        if response.tool_calls:
            tool_names = [tc["name"] for tc in response.tool_calls]
            logger.info(
                "[LLM Node] LLM chose to call tools: %s",
                tool_names,
            )
            await record_activity_from_context(
                "ai_engine",
                f"LLM selected {len(tool_names)} tool(s)",
                status="succeeded",
                metadata={
                    "stage": "llm_decision",
                    "decision": "tool_call",
                    "tool_names": tool_names,
                    "response_preview": raw_text[:200] if raw_text else None,
                },
            )
        else:
            logger.debug(
                "[LLM Node] LLM responded with content: '%s...'",
                raw_text[:200],
            )
            await record_activity_from_context(
                "ai_engine",
                "LLM returned text response",
                status="succeeded",
                metadata={
                    "stage": "llm_decision",
                    "decision": "text_response",
                    "response_preview": raw_text[:200],
                },
            )

    # MessagesState handles appending the response message automatically
    return {
        "messages": [response],
        "tools": [t.name for t in allowed_tools],
        "raw_response": raw_text,
    }


# ---------------------------------------------------------------------------
# MCP tool name helpers
# ---------------------------------------------------------------------------

def _is_mcp_tool(tool: BaseTool) -> bool:
    """Return True if *tool* is an MCP-originated tool (prefixed ``mcp__``)."""
    return tool.name.startswith("mcp__")


def _mcp_slug(tool: BaseTool) -> str:
    """Extract the connector slug from an MCP-prefixed tool name.

    ``mcp__github__list_repos`` → ``github``
    """
    parts = tool.name.split("__", 2)
    return parts[1] if len(parts) >= 3 else ""
