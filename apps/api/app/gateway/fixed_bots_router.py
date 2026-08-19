"""API router for fixed Slack bot metadata.

Exposes a public endpoint that returns the list of available fixed bot
identities so the frontend can render the bot picker UI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.gateway.fixed_bots import get_fixed_bot, list_all_bots

router = APIRouter(prefix="/api/fixed-bots", tags=["fixed-bots"])


class FixedBotResponse(BaseModel):
    """Public metadata for a fixed bot (credentials are never exposed)."""

    name: str
    role: str
    employee_type: str
    description: str
    is_configured: bool


@router.get("", response_model=list[FixedBotResponse])
async def list_fixed_bots(
    current_user: User = Depends(get_current_user),
) -> list[FixedBotResponse]:
    """Return the list of all fixed bot identities.

    The frontend uses this to render the bot picker grid on the onboarding
    page.  Only bots whose credentials are fully configured can be installed.
    """
    bots = list_all_bots()
    return [
        FixedBotResponse(
            name=bot.name,
            role=bot.role,
            employee_type=bot.employee_type,
            description=bot.description,
            is_configured=bot.is_configured,
        )
        for bot in bots
    ]
