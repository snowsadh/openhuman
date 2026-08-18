from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.memory.service import (
    add_user_to_tenant,
    create_dataset,
    create_system_user,
    create_tenant,
    forget_dataset,
    get_or_create_admin,
    grant_tenant_read,
    remember,
)
from app.organizations.models import Organization
from app.organizations.schemas import CreateOrganizationRequest, UpdateOrganizationRequest

logger = logging.getLogger(__name__)


async def create_org(
    db: AsyncSession, user_id: UUID, data: CreateOrganizationRequest
) -> Organization:
    org = Organization(
        owner_id=user_id,
        name=data.name,
        description=data.description,
        what_it_does=data.what_it_does,
        website_url=data.website_url,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    # ── Cognee provisioning (best-effort, non-blocking) ──────────────────
    try:
        admin = await get_or_create_admin()
        tenant = await create_tenant(org.name, admin["id"])
        sys_user = await create_system_user(tenant["id"], admin["id"])
        await add_user_to_tenant(sys_user["id"], tenant["id"], admin["id"])
        dataset = await create_dataset(
            f"company-{tenant['id']}", sys_user["id"]
        )
        await grant_tenant_read(dataset["id"], tenant["id"], sys_user["id"])

        # Seed org info as a memory fact
        seed_text = f"Organization: {org.name}"
        if org.description:
            seed_text += f"\nDescription: {org.description}"
        if org.what_it_does:
            seed_text += f"\nWhat it does: {org.what_it_does}"
        await remember(
            seed_text,
            f"company-{tenant['id']}",
            sys_user["id"],
            dataset_id=dataset["id"],
            background=True,
        )

        # Persist Cognee IDs on org row
        org.cognee_tenant_id = tenant["id"]
        org.cognee_tenant_name = tenant["name"]
        org.cognee_system_user_id = sys_user["id"]
        org.cognee_system_user_name = sys_user["email"]
        org.cognee_dataset_id = dataset["id"]
        org.cognee_dataset_name = dataset["name"]
        await db.commit()
        await db.refresh(org)
    except Exception:
        logger.exception(
            "Cognee org provisioning failed for org %s (non-blocking)", org.id
        )
    # ── End Cognee ──────────────────────────────────────────────────────

    # ── Website URL ingest (best-effort, only if Cognee succeeded) ──────────
    # Cognee's remember() natively accepts HTTP/HTTPS URLs — it fetches and
    # ingests page content automatically. No extra scraping package needed.
    if data.website_url and org.cognee_dataset_name and org.cognee_system_user_id:
        try:
            await remember(
                data.website_url,
                org.cognee_dataset_name,
                org.cognee_system_user_id,
                dataset_id=org.cognee_dataset_id,
                background=True,
            )
        except Exception:
            logger.exception(
                "Website URL ingest failed for org %s (non-blocking)", org.id
            )
    # ── End website ingest ─────────────────────────────────────────────────

    return org



async def get_org(db: AsyncSession, org_id: UUID, user_id: UUID) -> Organization | None:
    return await db.scalar(
        select(Organization)
        .options(selectinload(Organization.employees))
        .where(
            Organization.id == org_id, Organization.owner_id == user_id
        )
    )


async def list_orgs(db: AsyncSession, user_id: UUID) -> list[Organization]:
    result = await db.execute(
        select(Organization)
        .where(Organization.owner_id == user_id)
        .order_by(Organization.created_at.desc())
    )
    return list(result.scalars().all())


async def update_org(
    db: AsyncSession, org_id: UUID, user_id: UUID, data: UpdateOrganizationRequest
) -> Organization | None:
    org = await get_org(db, org_id, user_id)
    if org is None:
        return None
    if data.name is not None:
        org.name = data.name
    if data.description is not None:
        org.description = data.description
    if data.what_it_does is not None:
        org.what_it_does = data.what_it_does
    if data.website_url is not None:
        old_url = org.website_url
        org.website_url = data.website_url
        # Re-ingest if URL changed and Cognee is provisioned
        if data.website_url != old_url and org.cognee_dataset_name and org.cognee_system_user_id:
            try:
                await remember(
                    data.website_url,
                    org.cognee_dataset_name,
                    org.cognee_system_user_id,
                    dataset_id=org.cognee_dataset_id,
                    background=True,
                )
            except Exception:
                logger.exception(
                    "Website URL re-ingest failed for org %s (non-blocking)", org.id
                )
    await db.commit()
    await db.refresh(org)
    return org


async def delete_org(db: AsyncSession, org_id: UUID, user_id: UUID) -> bool:
    org = await get_org(db, org_id, user_id)
    if org is None:
        return False

    # ── Best-effort Cognee cleanup before cascade delete ────────────────
    tasks: list = []
    for emp in org.employees:
        if emp.cognee_dataset_name:
            tasks.append(forget_dataset(emp.cognee_dataset_name))  # type: ignore[arg-type]
    if org.cognee_dataset_name:
        tasks.append(forget_dataset(org.cognee_dataset_name))
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.exception(
                    "Cognee forget_dataset failed during org delete %s",
                    org.id,
                    exc_info=result,
                )
    # ─────────────────────────────────────────────────────────────────────

    await db.delete(org)
    await db.commit()
    return True
