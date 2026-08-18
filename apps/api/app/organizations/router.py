from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.service import record_activity
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.organizations.schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    UpdateOrganizationRequest,
)
from app.organizations.service import (
    create_org,
    delete_org,
    get_org,
    list_orgs,
    update_org,
)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: CreateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrganizationResponse:
    org = await create_org(db, current_user.id, data)
    try:
        await record_activity(
            db, org.id, "org_created",
            f"Organization '{org.name}' created",
            platform="api",
            metadata={"name": org.name},
        )
    except Exception:
        pass
    return org  # type: ignore[return-value]


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[OrganizationResponse]:
    return await list_orgs(db, current_user.id)  # type: ignore[return-value]


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrganizationResponse:
    org = await get_org(db, org_id, current_user.id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org  # type: ignore[return-value]


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    data: UpdateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrganizationResponse:
    org = await update_org(db, org_id, current_user.id, data)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    try:
        await record_activity(
            db, org.id, "org_updated",
            f"Organization '{org.name}' updated",
            platform="api",
            metadata={"name": org.name},
        )
    except Exception:
        pass
    return org  # type: ignore[return-value]


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    org = await get_org(db, org_id, current_user.id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Record activity BEFORE delete (FK constraint)
    try:
        await record_activity(
            db, org_id, "org_deleted",
            f"Organization '{org.name}' deleted",
            platform="api",
            metadata={"name": org.name},
        )
    except Exception:
        pass

    deleted = await delete_org(db, org_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
