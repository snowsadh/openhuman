"""Memory-conscious authenticated agent endpoint for constrained Zop containers."""

from __future__ import annotations

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.employees.models import Employee
from app.organizations.models import Organization

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
    """Run an authorized employee prompt through OpenAI without heavy graph imports."""
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

    system_prompt = data.system_prompt_template or (
        f"You are {employee.name}, {employee.role or 'an AI assistant'}. "
        "Be accurate, concise, and helpful."
    )
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": data.content},
                    ],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI returned HTTP {exc.response.status_code}",
        ) from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI request failed",
        ) from exc

    content = payload["choices"][0]["message"]["content"]
    return AgentResponse(response=content, tool_calls_count=0)
