"""Memory-conscious authenticated agent endpoint for constrained Zop containers."""

from __future__ import annotations

from uuid import UUID

from armoriq_sdk.exceptions import ArmorIQException
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity
from app.auth.models import User
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.employees.models import Employee
from app.organizations.models import Organization
from app.zop_armoriq import ArmorIQRuntimeError, generate_response_through_armoriq

router = APIRouter(prefix="/api/agent", tags=["agent"])


class MessageInput(BaseModel):
    content: str
    platform: str
    channel_id: str
    user_id: str
    employee_id: UUID
    employee_name: str | None = None
    org_name: str | None = None
    system_prompt_template: str | None = None


class AgentResponse(BaseModel):
    response: str | None
    files: list[dict] = Field(default_factory=list)
    tool_calls_count: int = 0
    error: str | None = None


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    data: MessageInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentResponse:
    """Run an authorized employee response through ArmorIQ's MCP boundary."""
    employee = await db.scalar(
        select(Employee)
        .join(Organization, Organization.id == Employee.org_id)
        .where(
            Employee.id == data.employee_id,
            Organization.owner_id == current_user.id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee must be active",
        )
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI is not configured",
        )
    if not settings.armoriq_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ArmorIQ is not configured",
        )

    system_prompt = data.system_prompt_template or (
        f"You are {employee.name}, {employee.role or 'an AI assistant'}. "
        "Be accurate, concise, and helpful."
    )
    try:
        content, plan_hash = await generate_response_through_armoriq(
            content=data.content,
            system_prompt=system_prompt,
            employee_id=str(employee.id),
            user_email=current_user.email,
        )
    except (ArmorIQException, ArmorIQRuntimeError) as exc:
        try:
            await record_activity(
                db,
                employee.org_id,
                "armoriq_blocked",
                f"ArmorIQ blocked response generation for {employee.name}",
                employee_id=employee.id,
                employee_name=employee.name,
                platform=data.platform,
                status="blocked",
                metadata={"reason_type": type(exc).__name__},
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ArmorIQ governance failed closed",
        ) from exc

    await record_activity(
        db,
        employee.org_id,
        "armoriq_plan",
        "ArmorIQ signed the response-generation plan",
        employee_id=employee.id,
        employee_name=employee.name,
        platform=data.platform,
        status="succeeded",
        metadata={"mcp": "openhuman-zop", "action": "generate_response"},
    )
    await record_activity(
        db,
        employee.org_id,
        "armoriq_allowed",
        "ArmorIQ allowed governed response generation",
        employee_id=employee.id,
        employee_name=employee.name,
        platform=data.platform,
        status="succeeded",
        metadata={
            "mcp": "openhuman-zop",
            "action": "generate_response",
            "plan_hash": plan_hash,
        },
    )
    return AgentResponse(response=content, tool_calls_count=1)
