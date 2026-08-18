from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.channel_assignments.schemas import ChannelAssignmentResponse
from app.agent.jobs.models import AgentJob
from app.agent.tools.mcp.models import McpConnection
from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.employees.models import Employee
from app.employees.schemas import (
    CreateEmployeeRequest,
    EmployeeResponse,
    UpdateEmployeeRequest,
)
from app.gateway.fixed_bots import get_fixed_bot
from app.memory.service import (
    add_user_to_tenant,
    create_dataset,
    create_employee_user,
    forget_dataset,
    get_or_create_admin,
    grant_tenant_read,
    remember,
)
from app.organizations.models import Organization

logger = logging.getLogger(__name__)


def _build_employee_profile(emp: Employee) -> str:
    """Serialize employee identity fields to JSON for Cognee profile seed."""
    return json.dumps({
        "name": emp.name,
        "role": emp.role,
        "employee_type": emp.employee_type,
        "personality": emp.personality,
        "specialization": emp.specialization,
    })

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DuplicateEmployeeTypeError(Exception):
    """Raised when creating/updating an employee to a type already used by the org."""


# PoolExhaustionError removed — slot-based provisioning is deprecated
# in favor of the fixed-bot architecture.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_org(db: AsyncSession, org_id: UUID, user_id: UUID) -> Organization | None:
    """Return the org only if it belongs to user_id."""
    return await db.scalar(
        select(Organization).where(
            Organization.id == org_id, Organization.owner_id == user_id
        )
    )


async def _get_employee_with_assignments(
    db: AsyncSession, emp_id: UUID, org_id: UUID
) -> Employee | None:
    """Fetch an employee with channel_assignments eagerly loaded."""
    return await db.scalar(
        select(Employee)
        .where(Employee.id == emp_id, Employee.org_id == org_id)
        .options(selectinload(Employee.channel_assignments))
    )


def _to_response(
    emp: Employee,
    *,
    operational_status: str = "offline",
    current_task: str | None = None,
    last_run_at=None,
    last_error: str | None = None,
    mcp_connections: list | None = None,
) -> EmployeeResponse:
    """Build EmployeeResponse from ORM object, masking raw tokens."""
    return EmployeeResponse(
        id=emp.id,
        org_id=emp.org_id,
        name=emp.name,
        employee_type=emp.employee_type,
        role=emp.role,
        personality=emp.personality,
        specialization=emp.specialization,
        duties=emp.duties,
        memory_policy=emp.memory_policy,
        escalation_policy=emp.escalation_policy,
        mcp_connections=mcp_connections or [],
        status=emp.status,
        has_discord_token=emp.discord_token_enc is not None,
        has_slack_token=emp.slack_token_enc is not None,
        slack_team_name=emp.slack_team_name,
        slack_bot_user_id=emp.slack_bot_user_id,
        cognee_user_id=emp.cognee_user_id,
        cognee_dataset_name=emp.cognee_dataset_name,
        channel_assignments=[
            ChannelAssignmentResponse.model_validate(ca, from_attributes=True)
            for ca in (emp.channel_assignments or [])
        ],
        created_at=emp.created_at,
        updated_at=emp.updated_at,
        operational_status=operational_status,
        current_task=current_task,
        last_run_at=last_run_at,
        last_error=last_error,
    )


async def _to_response_with_runtime(db: AsyncSession, emp: Employee) -> EmployeeResponse:
    running = await db.scalar(
        select(AgentJob).where(
            AgentJob.employee_id == emp.id,
            AgentJob.status.in_(["running", "awaiting_approval"]),
        ).order_by(AgentJob.started_at.desc().nullslast(), AgentJob.created_at.desc())
    )
    last = running or await db.scalar(
        select(AgentJob).where(
            AgentJob.employee_id == emp.id,
            AgentJob.job_type != "cronjob",
        )
        .order_by(AgentJob.created_at.desc())
    )
    if emp.status != "active":
        operational_status = "offline"
    elif running is not None:
        operational_status = "working"
    elif last is not None and last.status == "failed":
        operational_status = "attention"
    else:
        operational_status = "idle"
    current_task = None
    if running is not None:
        current_task = (
            running.user_text or (running.payload or {}).get("schedule_name") or running.job_type
        )[:160]

    connections = list((await db.execute(
        select(McpConnection).where(
            McpConnection.org_id == emp.org_id,
            McpConnection.status == "connected",
            or_(McpConnection.employee_id == emp.id, McpConnection.employee_id.is_(None)),
        ).order_by(McpConnection.created_at)
    )).scalars().all())
    return _to_response(
        emp,
        operational_status=operational_status,
        current_task=current_task,
        last_run_at=(last.finished_at or last.started_at or last.created_at) if last else None,
        last_error=last.error if last and last.status == "failed" else None,
        mcp_connections=[{
            "id": str(connection.id),
            "connector_slug": connection.connector_slug,
            "status": connection.status,
        } for connection in connections],
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_employee(
    db: AsyncSession, org_id: UUID, user_id: UUID, data: CreateEmployeeRequest
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None

    # Enforce one employee per type per organization
    if data.employee_type:
        existing = await db.scalar(
            select(Employee).where(
                Employee.org_id == org_id,
                Employee.employee_type == data.employee_type,
            )
        )
        if existing is not None:
            raise DuplicateEmployeeTypeError(
                f"An employee of type '{data.employee_type}' already exists in this organization."
            )

    # Fixed mode: override name/role from the fixed bot registry
    emp_name = data.name
    emp_role = data.role
    if settings.slack_identity_mode == "fixed" and data.employee_type:
        fixed_bot = get_fixed_bot(data.employee_type)
        if fixed_bot:
            emp_name = fixed_bot.name
            emp_role = fixed_bot.role

    # `get_template()` resolves prompts/tools/duties by `specialization`, not
    # `employee_type`. Default it from `employee_type` (their slugs match the
    # template registry keys) so employees created without an explicit
    # specialization still load the correct template instead of silently
    # falling back to GENERAL_TEMPLATE.
    emp = Employee(
        org_id=org_id,
        name=emp_name,
        role=emp_role,
        personality=data.personality,
        specialization=data.specialization or data.employee_type,
        employee_type=data.employee_type,
        duties=data.duties,
        memory_policy=data.memory_policy,
        escalation_policy=data.escalation_policy,
    )
    db.add(emp)
    await db.flush()


    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "ix_employees_org_id_employee_type" in str(exc):
            raise DuplicateEmployeeTypeError(
                f"An employee of type '{data.employee_type}' already exists in this organization."
            ) from exc
        raise

    # ── Cognee provisioning (best-effort, only if org has tenant) ──────
    if org.cognee_tenant_id:
        try:
            admin = await get_or_create_admin()
            cognee_user = await create_employee_user(
                org.cognee_tenant_id, emp.name
            )
            await add_user_to_tenant(
                cognee_user["id"], org.cognee_tenant_id, admin["id"]
            )
            dataset = await create_dataset(
                f"employee-{emp.id}", cognee_user["id"]
            )
            await grant_tenant_read(
                dataset["id"], org.cognee_tenant_id, cognee_user["id"]
            )

            # Seed employee profile
            profile = _build_employee_profile(emp)
            await remember(
                profile,
                f"employee-{emp.id}",
                cognee_user["id"],
                dataset_id=dataset["id"],
                background=True,
            )

            # Persist Cognee IDs on employee row
            emp.cognee_user_id = cognee_user["id"]
            emp.cognee_user_name = cognee_user["email"]
            emp.cognee_dataset_id = dataset["id"]
            emp.cognee_dataset_name = dataset["name"]
            await db.commit()
        except Exception:
            logger.exception(
                "Cognee employee provisioning failed for emp %s "
                "(non-blocking)",
                emp.id,
            )
    # ── End Cognee ──────────────────────────────────────────────────────

    # Re-fetch with relationships
    emp = await _get_employee_with_assignments(db, emp.id, org_id)  # type: ignore[assignment]
    return await _to_response_with_runtime(db, emp)  # type: ignore[arg-type]


async def get_employee(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    emp = await _get_employee_with_assignments(db, emp_id, org_id)
    if emp is None:
        return None
    return await _to_response_with_runtime(db, emp)


async def get_employee_model(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID
) -> Employee | None:
    """Fetch the raw employee model after verifying org ownership."""
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    return await db.scalar(
        select(Employee).where(Employee.id == emp_id, Employee.org_id == org_id)
    )


async def list_employees(
    db: AsyncSession, org_id: UUID, user_id: UUID
) -> list[EmployeeResponse] | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    result = await db.execute(
        select(Employee)
        .where(Employee.org_id == org_id)
        .options(selectinload(Employee.channel_assignments))
        .order_by(Employee.created_at.desc())
    )
    return [await _to_response_with_runtime(db, e) for e in result.scalars().all()]


_ALLOWED_STATUSES = {"active", "inactive", "suspended"}


async def update_employee(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID, data: UpdateEmployeeRequest
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    emp = await _get_employee_with_assignments(db, emp_id, org_id)
    if emp is None:
        return None

    # If employee_type is being changed, check for conflicts
    if data.employee_type is not None and data.employee_type != emp.employee_type:
        existing = await db.scalar(
            select(Employee).where(
                Employee.org_id == org_id,
                Employee.employee_type == data.employee_type,
                Employee.id != emp_id,
            )
        )
        if existing is not None:
            raise DuplicateEmployeeTypeError(
                f"An employee of type '{data.employee_type}' already exists in this organization."
            )

    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field == "status" and value not in _ALLOWED_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_ALLOWED_STATUSES)}"
            )
        setattr(emp, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "ix_employees_org_id_employee_type" in str(exc):
            raise DuplicateEmployeeTypeError(
                f"An employee of type '{data.employee_type}' already exists in this organization."
            ) from exc
        raise

    # ── Re-seed Cognee profile if identity fields changed ───────────────
    cognee_changed = any(
        field in update_data
        for field in (
            "name", "role", "employee_type",
            "personality", "specialization",
        )
    )
    if cognee_changed and emp.cognee_user_id and emp.cognee_dataset_name:
        try:
            profile = _build_employee_profile(emp)
            await remember(
                profile,
                emp.cognee_dataset_name,
                emp.cognee_user_id,
                dataset_id=emp.cognee_dataset_id,
                background=True,
            )
        except Exception:
            logger.exception(
                "Cognee profile re-seed failed for emp %s (non-blocking)",
                emp.id,
            )
    # ── End Cognee ──────────────────────────────────────────────────────

    # ── Slack app manifest rename removed ─────────────────────────────────
    # (per_employee mode is deprecated; manifest rename via Slack API is
    #  no longer supported in the fixed-bot architecture.)

    emp = await _get_employee_with_assignments(db, emp_id, org_id)  # type: ignore[arg-type]
    return await _to_response_with_runtime(db, emp)  # type: ignore[arg-type]


async def delete_employee(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID
) -> bool:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return False
    emp = await db.scalar(
        select(Employee).where(Employee.id == emp_id, Employee.org_id == org_id)
    )
    if emp is None:
        return False

    # (Slot release removed — fixed mode has no slots to release)

    # ── Best-effort Cognee cleanup ──────────────────────────────────────
    if emp.cognee_dataset_name:
        try:
            await forget_dataset(emp.cognee_dataset_name)
        except Exception:
            logger.exception(
                "Cognee forget_dataset failed during employee delete %s",
                emp.id,
            )
    # ─────────────────────────────────────────────────────────────────────

    await db.delete(emp)
    await db.commit()
    return True


async def store_discord_token(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID, token: str
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    emp = await _get_employee_with_assignments(db, emp_id, org_id)
    if emp is None:
        return None
    emp.discord_token_enc = encrypt_token(token)
    await db.commit()
    emp = await _get_employee_with_assignments(db, emp_id, org_id)  # type: ignore[assignment]
    return await _to_response_with_runtime(db, emp)  # type: ignore[arg-type]


async def store_slack_token(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID, token: str
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    emp = await _get_employee_with_assignments(db, emp_id, org_id)
    if emp is None:
        return None
    emp.slack_token_enc = encrypt_token(token)
    await db.commit()
    emp = await _get_employee_with_assignments(db, emp_id, org_id)  # type: ignore[assignment]
    return await _to_response_with_runtime(db, emp)  # type: ignore[arg-type]


async def update_status(
    db: AsyncSession, org_id: UUID, emp_id: UUID, user_id: UUID, new_status: str
) -> EmployeeResponse | None:
    org = await _get_org(db, org_id, user_id)
    if org is None:
        return None
    emp = await _get_employee_with_assignments(db, emp_id, org_id)
    if emp is None:
        return None
    emp.status = new_status
    await db.commit()
    emp = await _get_employee_with_assignments(db, emp_id, org_id)  # type: ignore[assignment]
    return await _to_response_with_runtime(db, emp)  # type: ignore[arg-type]


async def get_employee_raw(
    db: AsyncSession, emp_id: UUID
) -> Employee | None:
    """Fetch raw Employee ORM object (used by gateway to read encrypted tokens)."""
    return await db.scalar(select(Employee).where(Employee.id == emp_id))


async def get_active_employees_with_tokens(db: AsyncSession) -> list[Employee]:
    """Return all active employees that have at least one bot token. Used by gateway."""
    result = await db.execute(
        select(Employee)
        .where(
            Employee.status == "active",
            (Employee.discord_token_enc.is_not(None)) | (Employee.slack_token_enc.is_not(None)),
        )
    )
    return list(result.scalars().all())


def decrypt_discord_token(emp: Employee) -> str | None:
    """Decrypt the Discord token for a given employee. Returns None if not set."""
    if emp.discord_token_enc is None:
        return None
    return decrypt_token(emp.discord_token_enc)


def decrypt_slack_token(emp: Employee) -> str | None:
    """Decrypt the Slack token for a given employee. Returns None if not set."""
    if emp.slack_token_enc is None:
        return None
    return decrypt_token(emp.slack_token_enc)
