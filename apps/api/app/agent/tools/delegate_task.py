"""Sub-agent delegation tool.

Spawns a child agent with an isolated conversation context. The child gets
a focused system prompt built from the delegated goal + context and runs
through the same LangGraph agent graph.

Supports two roles:
  - ``leaf`` (default): focused worker, cannot call ``delegate_task`` further.
  - ``orchestrator``: retains the delegation toolset and can spawn its own
    workers, bounded by ``MAX_SPAWN_DEPTH``.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.build import build_graph
from app.agent.state import AgentState
from app.employees.models import Employee
from app.employees.templates import get_employee_template

logger = logging.getLogger(__name__)

MAX_SPAWN_DEPTH = 3
MAX_CONCURRENT_CHILDREN = 5


@tool
async def delegate_task(
    goal: str,
    context: str | None = None,
    role: str = "leaf",
    config: RunnableConfig | None = None,
) -> str:
    """Spawn a sub-agent to work on a task independently.
    The sub-agent runs with its own isolated context and returns its final
    response. Use this when a task is self-contained enough that a focused
    sub-agent can handle it.

    Args:
        goal: What the sub-agent should accomplish. Be specific and
            self-contained — the sub-agent knows nothing about conversation
            history.
        context: Background information the sub-agent needs: file paths,
            error messages, project structure, constraints.
        role: Controls whether the child can further delegate. ``"leaf"``
            (default) cannot; ``"orchestrator"`` retains the delegation toolset.
    """
    if role not in ("leaf", "orchestrator"):
        return f"Invalid role '{role}'. Must be 'leaf' or 'orchestrator'."

    if not goal or not goal.strip():
        return "Goal is required for delegation."

    configurable = (config or {}).get("configurable", {})
    db: AsyncSession | None = configurable.get("db")
    employee_id_str = configurable.get("employee_id")
    parent_depth = configurable.get("delegate_depth", 0)
    platform = configurable.get("platform", "api")
    channel_id = configurable.get("channel_id", "delegation")

    if parent_depth >= MAX_SPAWN_DEPTH:
        return (
            f"Delegation depth limit reached (depth={parent_depth}, "
            f"max={MAX_SPAWN_DEPTH}). Cannot spawn further sub-agents."
        )

    # Resolve employee template for tool gating
    child_tools: list = []
    if db and employee_id_str:
        emp = await db.scalar(
            select(Employee).where(Employee.id == UUID(employee_id_str))
        )
        if emp:
            template = get_employee_template(emp)
            from app.agent.tools.executor import BUILT_IN_TOOLS
            allowed_names = set(template.allowed_tools)
            child_tools = [
                t for t in BUILT_IN_TOOLS
                if t.name in allowed_names
            ]
    else:
        from app.agent.tools.executor import BUILT_IN_TOOLS
        child_tools = list(BUILT_IN_TOOLS)

    # Leaf agents cannot delegate or schedule
    if role == "leaf":
        child_tools = [
            t for t in child_tools
            if t.name not in ("delegate_task", "cronjob", "escalate_to_human")
        ]

    child_graph = build_graph(child_tools)

    child_system_prompt = (
        "You are a focused sub-agent working on a delegated task.\n\n"
        f"## Goal\n{goal.strip()}\n"
    )
    if context and context.strip():
        child_system_prompt += f"\n## Context\n{context.strip()}\n"

    child_state: AgentState = {
        "messages": [SystemMessage(content=child_system_prompt)],
        "platform": platform,
        "employee_id": employee_id_str or "delegation",
        "tool_round": 0,
    }

    child_config = {
        "configurable": {
            "db": db,
            "employee_id": employee_id_str,
            "all_tools": child_tools,
            "thread_id": f"{configurable.get('thread_id', 'delegate')}__child",
            "platform": platform,
            "channel_id": channel_id,
            "delegate_depth": parent_depth + 1,
        }
    }

    try:
        result = await child_graph.ainvoke(child_state, config=child_config)
        response = result.get("response") or result.get("raw_response") or ""
        tool_rounds = result.get("tool_round", 0)
        files = result.get("files", [])
        error = result.get("error")
        summary = (
            f"\n\n## Sub-agent Result\n{response}"
        )
        if files:
            summary += f"\n\nFiles generated: {[f.get('filename') for f in files]}"
        if tool_rounds:
            summary += f"\n\nTool rounds used by sub-agent: {tool_rounds}"
        if error:
            summary += f"\n\nSub-agent error: {error}"
        return summary
    except Exception as exc:
        logger.exception("delegate_task sub-agent failed")
        return f"Sub-agent execution failed: {exc}"
