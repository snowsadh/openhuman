from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.context import activity_employee_id, activity_org_id
from app.activity.models import ActivityEvent
from app.agent.jobs.models import AgentJob
from app.core.config import settings
from app.core.database import async_session_factory
from app.employees.models import Employee
from app.governance.models import ApprovalAssignment, ApprovalRequest
from app.organizations.models import Organization

_SENSITIVE_KEYS = {
    "authorization",
    "body",
    "content",
    "credential",
    "credentials",
    "customer",
    "email_content",
    "message",
    "password",
    "secret",
    "token",
}


def redact_parameters(value: Any, key: str = "") -> Any:
    """Retain useful shape while removing credentials and message/customer data."""
    normalized = key.lower().replace("-", "_")
    if any(fragment in normalized for fragment in _SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): redact_parameters(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_parameters(item, key) for item in value[:25]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:80]}…[redacted {len(value) - 80} chars]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def armoriq_record_url(plan_hash: str, delegation_id: str | None = None) -> str:
    base = settings.armoriq_dashboard_url.rstrip("/")
    if delegation_id:
        return f"{base}/dashboard/plans?delegation={delegation_id}"
    return f"{base}/dashboard/plans?plan={plan_hash}"


async def persist_hold_from_context(
    *,
    plan_hash: str,
    token_id: str | None,
    mcp: str,
    action: str,
    parameters: Any,
    requester_email: str | None,
    hold: dict[str, Any],
    job_id: str | None,
) -> None:
    """Mirror an ArmorIQ hold without granting or executing it locally."""
    org_value = activity_org_id.get()
    if not org_value:
        return
    employee_value = activity_employee_id.get()
    org_id = UUID(org_value)
    employee_id = UUID(employee_value) if employee_value else None
    now = datetime.now(UTC)

    async with async_session_factory() as db:
        existing = await db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.org_id == org_id,
                ApprovalRequest.plan_hash == plan_hash,
                ApprovalRequest.mcp == mcp,
                ApprovalRequest.action == action,
            )
        )
        if existing is not None:
            existing.delegation_id = hold.get("delegation_id") or existing.delegation_id
            existing.reason = str(hold.get("reason") or "ArmorIQ approval required")[:1000]
            existing.updated_at = now
            await db.commit()
            return

        agent_type = "general"
        if employee_id:
            employee = await db.get(Employee, employee_id)
            agent_type = employee.employee_type or "general" if employee else "general"
        assignment = await db.scalar(
            select(ApprovalAssignment).where(
                ApprovalAssignment.org_id == org_id,
                ApprovalAssignment.agent_type == agent_type,
            )
        )
        organization = await db.get(Organization, org_id)
        approver_id = (
            assignment.approver_user_id
            if assignment is not None
            else organization.owner_id if organization is not None else None
        )
        parsed_job_id: UUID | None = None
        if job_id:
            try:
                parsed_job_id = UUID(job_id)
            except ValueError:
                parsed_job_id = None

        request = ApprovalRequest(
            org_id=org_id,
            employee_id=employee_id,
            job_id=parsed_job_id,
            plan_hash=plan_hash,
            token_id=token_id,
            delegation_id=hold.get("delegation_id"),
            mcp=mcp,
            action=action,
            redacted_parameters=redact_parameters(parameters),
            requester_email=requester_email,
            assigned_approver_id=approver_id,
            status="pending",
            reason=str(hold.get("reason") or "ArmorIQ approval required")[:1000],
            armoriq_url=armoriq_record_url(plan_hash, hold.get("delegation_id")),
            expires_at=now + timedelta(seconds=settings.armoriq_approval_timeout_seconds),
        )
        db.add(request)
        if parsed_job_id:
            job = await db.get(AgentJob, parsed_job_id)
            if job is not None:
                job.status = "awaiting_approval"
        await db.commit()


async def update_approval_execution_from_context(
    *,
    plan_hash: str,
    mcp: str,
    action: str,
    status: str,
    result: Any = None,
) -> None:
    org_value = activity_org_id.get()
    if not org_value:
        return
    async with async_session_factory() as db:
        request = await db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.org_id == UUID(org_value),
                ApprovalRequest.plan_hash == plan_hash,
                ApprovalRequest.mcp == mcp,
                ApprovalRequest.action == action,
            )
        )
        if request is None:
            return
        now = datetime.now(UTC)
        request.status = status
        request.decision = "approved" if status == "executed" else status
        request.decided_at = now
        if status == "executed":
            request.executed_at = now
            request.execution_result = redact_parameters(result)
        if request.job_id:
            job = await db.get(AgentJob, request.job_id)
            if job is not None:
                job.status = "succeeded" if status == "executed" else "failed"
        await db.commit()


async def expire_pending_approvals(db: AsyncSession, org_id: UUID) -> None:
    rows = list(
        (
            await db.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.org_id == org_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.expires_at <= datetime.now(UTC),
                )
            )
        ).all()
    )
    for row in rows:
        row.status = "expired"
        row.decision = "expired"
        row.decided_at = datetime.now(UTC)
    if rows:
        await db.commit()


async def build_armoriq_metrics(db: AsyncSession, org_id: UUID) -> dict[str, Any]:
    events = list(
        (
            await db.scalars(
                select(ActivityEvent)
                .where(
                    ActivityEvent.org_id == org_id,
                    ActivityEvent.event_type.like("armoriq_%"),
                )
                .order_by(ActivityEvent.occurred_at.desc())
                .limit(2000)
            )
        ).all()
    )
    event_counts = Counter(event.event_type for event in events)
    call_count = sum(
        event_counts[name]
        for name in ("armoriq_allowed", "armoriq_held", "armoriq_blocked")
    )
    agent_counts = Counter(event.employee_name or "Unassigned" for event in events)
    mcp_counts = Counter(
        str((event.metadata_ or {}).get("mcp"))
        for event in events
        if (event.metadata_ or {}).get("mcp")
    )
    tool_counts = Counter(
        str((event.metadata_ or {}).get("action"))
        for event in events
        if (event.metadata_ or {}).get("action")
    )
    pending = await db.scalar(
        select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.org_id == org_id,
            ApprovalRequest.status == "pending",
        )
    )

    def percentage(count: int) -> float:
        return round((count / call_count) * 100, 1) if call_count else 0.0

    plans = [event for event in events if event.event_type == "armoriq_plan"][:20]
    latest = events[0].occurred_at if events else None
    telemetry_healthy = bool(
        latest and latest >= datetime.now(UTC) - timedelta(hours=24)
    )
    registration_healthy = bool(
        settings.armoriq_api_key
        and settings.armoriq_mcp_bearer_token
        and settings.armoriq_mcp_public_url.startswith("https://")
    )
    return {
        "status": "healthy" if registration_healthy and telemetry_healthy else "degraded",
        "total_plans": event_counts["armoriq_plan"],
        "total_calls": call_count,
        "allow_count": event_counts["armoriq_allowed"],
        "hold_count": event_counts["armoriq_held"],
        "block_count": event_counts["armoriq_blocked"],
        "executed_count": event_counts["armoriq_executed"],
        "failed_count": event_counts["armoriq_failed"],
        "pending_approvals": int(pending or 0),
        "allow_percent": percentage(event_counts["armoriq_allowed"]),
        "hold_percent": percentage(event_counts["armoriq_held"]),
        "block_percent": percentage(event_counts["armoriq_blocked"]),
        "top_agents": [
            {"name": name, "count": count}
            for name, count in agent_counts.most_common(5)
        ],
        "top_mcps": [{"name": name, "count": count} for name, count in mcp_counts.most_common(5)],
        "top_tools": [{"name": name, "count": count} for name, count in tool_counts.most_common(5)],
        "recent_plans": [
            {
                "plan_hash": (event.metadata_ or {}).get("plan_hash"),
                "agent": event.employee_name,
                "occurred_at": event.occurred_at.isoformat(),
                "url": armoriq_record_url(str((event.metadata_ or {}).get("plan_hash") or "")),
            }
            for event in plans
        ],
        "registration_healthy": registration_healthy,
        "telemetry_healthy": telemetry_healthy,
    }
