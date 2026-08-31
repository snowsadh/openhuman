"""Agent run endpoint — resolves MCP tools per employee at request time."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.context import (
    activity_channel_id,
    activity_employee_id,
    activity_employee_name,
    activity_org_id,
    activity_platform,
)
from app.activity.service import record_activity
from app.agent.armoriq import agent_id_for_employee_kind
from app.agent.build import build_graph
from app.agent.schemas import AgentResponse, MessageInput
from app.agent.tools.executor import BUILT_IN_TOOLS
from app.agent.tools.mcp.client import MCPClientManager, ResolvedConnection
from app.agent.tools.mcp.connectors import REGISTRY
from app.agent.tools.mcp.models import McpConnection
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import decrypt_token
from app.employees.models import Employee
from app.employees.templates import get_employee_template, get_template
from app.organizations.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# Public helper — used by bot gateways in-process
# ---------------------------------------------------------------------------


async def get_graph_for_employee(
    db: AsyncSession,
    employee_id: UUID,
) -> tuple[CompiledStateGraph, list]:
    """Resolve the right compiled graph + tool set for *employee_id*.

    Returns ``(graph, all_tools)`` where *all_tools* should be passed in
    ``config["configurable"]["all_tools"]`` so ``llm_call_node`` can filter
    by the employee's template.

    Bot gateways call this directly instead of importing a module-level graph.
    """
    emp = await db.scalar(select(Employee).where(Employee.id == employee_id))
    if emp is not None:
        org_id = emp.org_id
        template = get_employee_template(emp)
    else:
        org_id = None
        template = get_template("general")

    # Resolve MCP tools
    mcp_tools: list = []
    if org_id is not None and template.allowed_mcp_servers:
        mcp_tools = await _resolve_mcp_tools(db, org_id, employee_id, template.allowed_mcp_servers)

    all_tools = list(BUILT_IN_TOOLS) + mcp_tools
    # MCP tools retain connection-specific credentials, so compile this
    # employee's concrete tool instances into a request-local graph.
    graph = build_graph(all_tools)

    return graph, all_tools


# ---------------------------------------------------------------------------
# MCP tool resolution
# ---------------------------------------------------------------------------


async def _resolve_mcp_tools(
    db: AsyncSession,
    org_id: UUID,
    employee_id: UUID,
    allowed_mcp_servers: list[str],
) -> list:
    """Resolve MCP tools available to *employee_id*.

    1. Queries ``mcp_connections`` for org-wide + employee-specific rows.
    2. Filters by template ``allowed_mcp_servers``.
    3. Decrypts credentials and loads tools via ``MCPClientManager``.
    """
    if not allowed_mcp_servers:
        return []

    # Fetch connections: org-wide (employee_id IS NULL) + this employee
    result = await db.execute(
        select(McpConnection).where(
            McpConnection.org_id == org_id,
            McpConnection.status == "connected",
            McpConnection.verification_status == "verified",
            ((McpConnection.employee_id == employee_id) | (McpConnection.employee_id.is_(None))),
        )
    )
    rows: list[McpConnection] = list(result.scalars().all())

    if not rows:
        return []

    # Build resolved connections
    resolved: list[ResolvedConnection] = []
    for row in rows:
        # Template gate
        if "*" not in allowed_mcp_servers and row.connector_slug not in allowed_mcp_servers:
            continue

        spec = REGISTRY.get(row.connector_slug)
        if spec is None:
            logger.warning(
                "MCP connection references unknown connector slug '%s' — skipping",
                row.connector_slug,
            )
            continue

        # -- Lazy OAuth token refresh (before decrypting) -----------------
        if (
            spec.supports_token_refresh
            and row.auth_type == "oauth2"
            and row.oauth_refresh_token_enc
        ):
            try:
                from app.mcp.oauth import refresh_access_token

                refreshed = await refresh_access_token(spec, row)
                if refreshed is not None:
                    await db.commit()
                    logger.debug(
                        "Refreshed OAuth token for %s/%s",
                        row.connector_slug,
                        row.id,
                    )
            except Exception:
                logger.debug(
                    "Token refresh not attempted / failed for %s — using existing token",
                    row.connector_slug,
                )

        # Decrypt credentials if present
        creds: str | None = None
        if row.credentials_enc:
            try:
                creds = decrypt_token(row.credentials_enc)
            except Exception:
                logger.exception(
                    "Failed to decrypt credentials for MCP connection '%s'",
                    row.connector_slug,
                )
                continue

        resolved.append(
            ResolvedConnection(
                slug=row.connector_slug,
                connector=spec,
                credentials=creds,
                auth_type=row.auth_type,
                server_url=row.server_url,
            )
        )

    if not resolved:
        return []

    # Load tools — use the MCP slug as the server name so tools get
    # prefixed as ``mcp__{slug}__{tool}`` when ``tool_name_prefix=True``
    # is set on the client.
    mgr = MCPClientManager()
    try:
        tools = await mgr.connect(resolved)
    except Exception:
        logger.exception("Failed to connect to MCP servers")
        tools = []

    return tools


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    data: MessageInput,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AgentResponse:
    """Execute the authenticated internal AI agent test route.

    Requires a valid JWT bearer token. The route is intended for dashboard
    testing and development — production bot gateways call the graph
    in-process.
    """
    import time

    employee_id = data.employee_id
    authorized_employee = await db.scalar(
        select(Employee)
        .join(Organization, Organization.id == Employee.org_id)
        .where(Employee.id == employee_id, Organization.owner_id == _current_user.id)
    )
    if authorized_employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if authorized_employee.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee must be active")
    thread_key = f"{data.platform}:{employee_id}:{data.channel_id}"

    logger.info(
        "[Agent Run Start] Employee: %s | Platform: %s | Thread: %s",
        employee_id,
        data.platform,
        thread_key,
    )
    start_time = time.time()

    # Resolve the graph + tools for this employee
    graph, all_tools = await get_graph_for_employee(db, employee_id)

    # Construct initial LangGraph state
    initial_state = {
        "messages": [HumanMessage(content=data.content)],
        "platform": data.platform,
        "employee_id": str(employee_id),
        "tool_round": 0,
    }

    # Pass async DB session, employee context, and the FULL tool set so
    # llm_call_node can filter down to the employee-specific subset.
    config = {
        "configurable": {
            "db": db,
            "employee_id": str(employee_id),
            "all_tools": all_tools,
            "thread_id": thread_key,
            "platform": data.platform,
            "channel_id": data.channel_id,
            "armoriq_user_email": _current_user.email,
            "armoriq_agent_id": agent_id_for_employee_kind(authorized_employee.employee_type),
            "org_id": str(authorized_employee.org_id),
        }
    }

    # Resolve employee name + org for activity recording
    emp = await db.scalar(select(Employee).where(Employee.id == employee_id))
    employee_name = emp.name if emp else None
    emp_org_id = emp.org_id if emp else None

    # Thread recording context through graph nodes
    ctx_org_id = str(emp_org_id) if emp_org_id else None
    activity_org_id.set(ctx_org_id)
    activity_employee_id.set(str(employee_id))
    activity_employee_name.set(employee_name)
    activity_platform.set(data.platform)
    activity_channel_id.set(data.channel_id)

    if emp_org_id:
        try:
            await record_activity(
                db,
                emp_org_id,
                "ai_engine",
                "Agent run started",
                employee_id=employee_id,
                employee_name=employee_name,
                platform=data.platform,
                status="running",
                metadata={
                    "stage": "agent_run",
                    "thread_key": thread_key,
                    "channel_id": data.channel_id,
                    "user_id": data.user_id,
                },
            )
        except Exception:
            logger.exception("Failed to record agent run start activity")

    try:
        result_state = await graph.ainvoke(initial_state, config=config)

        elapsed = time.time() - start_time
        response_text = result_state.get("response")
        tool_rounds = result_state.get("tool_round", 0)
        error = result_state.get("error")

        logger.info(
            "[Agent Run Success] Employee: %s | Rounds: %d | Time: %.2fs | Error: %s",
            employee_id,
            tool_rounds,
            elapsed,
            error,
        )

        if emp_org_id:
            try:
                await record_activity(
                    db,
                    emp_org_id,
                    "ai_engine",
                    "Agent run completed",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="failed" if error else "succeeded",
                    metadata={
                        "stage": "agent_run",
                        "thread_key": thread_key,
                        "channel_id": data.channel_id,
                        "tool_rounds": tool_rounds,
                        "elapsed_seconds": round(elapsed, 3),
                        "error": error,
                    },
                )
            except Exception:
                logger.exception("Failed to record agent run completion activity")

        # Record guardrail events (best-effort)
        if emp_org_id and result_state.get("input_blocked"):
            try:
                await record_activity(
                    db,
                    emp_org_id,
                    "agent_conversation",
                    f"Input blocked: {result_state.get('block_reason', 'unknown')}",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="blocked",
                    metadata={"block_reason": result_state.get("block_reason")},
                )
            except Exception:
                pass

        if emp_org_id and not result_state.get("output_guardrail_passed", True):
            try:
                await record_activity(
                    db,
                    emp_org_id,
                    "agent_conversation",
                    "Output blocked by guardrail",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="blocked",
                )
            except Exception:
                pass

        # Record main conversation (best-effort, skip if already blocked)
        if emp_org_id and not result_state.get("input_blocked"):
            try:
                await record_activity(
                    db,
                    emp_org_id,
                    "agent_conversation",
                    f"Agent responded to: {data.content[:100]}",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="failed" if error else "succeeded",
                    description=json.dumps(
                        {
                            "response": response_text[:500] if response_text else None,
                            "tool_rounds": tool_rounds,
                            "error": error,
                            "channel_id": data.channel_id,
                        }
                    ),
                    metadata={
                        "tool_rounds": tool_rounds,
                        "user_id": data.user_id,
                        "channel_id": data.channel_id,
                    },
                )
            except Exception:
                logger.exception("Failed to record agent_conversation activity")

        return AgentResponse(
            response=response_text,
            files=result_state.get("files", []),
            tool_calls_count=tool_rounds,
            error=error,
        )
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.exception(
            "[Agent Run Failed] Employee: %s | Time: %.2fs | Error: %s",
            employee_id,
            elapsed,
            str(exc),
        )

        # Record failure activity (best-effort)
        if emp_org_id:
            try:
                await record_activity(
                    db,
                    emp_org_id,
                    "ai_engine",
                    "Agent run failed",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="failed",
                    metadata={
                        "stage": "agent_run",
                        "thread_key": thread_key,
                        "channel_id": data.channel_id,
                        "elapsed_seconds": round(elapsed, 3),
                        "error": str(exc),
                    },
                )
                await record_activity(
                    db,
                    emp_org_id,
                    "agent_conversation",
                    f"Agent error for: {data.content[:100]}",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    platform=data.platform,
                    status="failed",
                    description=json.dumps({"error": str(exc)}),
                    metadata={"error": str(exc)},
                )
            except Exception:
                pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent graph execution failed: {exc}",
        ) from exc
