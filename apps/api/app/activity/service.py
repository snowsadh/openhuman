from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import ActivityEvent
from app.activity.schemas import (
    ActivityEventResponse,
    ActivityFeedResponse,
    ActivityStatsResponse,
)

_PAGE_SIZE = 50
logger = logging.getLogger(__name__)

# Allowed event_type values — used to validate user input before SQL interpolation
_ALLOWED_EVENT_TYPES = frozenset({
    "ai_engine",
    "agent_run",
    "agent_conversation",
    "document_upload",
    "employee_created",
    "employee_updated",
    "tool_usage",
    "human_escalation",
    "memory_operation",
    "mcp_connected",
    "org_created",
    "org_updated",
    "org_deleted",
    "slack_oauth",
    "channel_assigned",
    "channel_unassigned",
})


# ── Recording helper ────────────────────────────────────────────────────────


async def record_activity(
    db: AsyncSession,
    org_id: UUID,
    event_type: str,
    summary: str,
    *,
    employee_id: UUID | None = None,
    employee_name: str | None = None,
    platform: str | None = None,
    status: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> ActivityEvent:
    """Insert a single activity event. Best-effort — raises on failure."""
    event = ActivityEvent(
        org_id=org_id,
        event_type=event_type,
        summary=summary,
        employee_id=employee_id,
        employee_name=employee_name,
        platform=platform,
        status=status,
        description=description,
        metadata_=metadata,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    return event


async def record_activity_from_context(
    event_type: str,
    summary: str,
    *,
    status: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Best-effort helper for graph nodes that only have contextvars available."""
    try:
        from app.activity.context import (
            activity_employee_id,
            activity_employee_name,
            activity_org_id,
            activity_platform,
        )
        from app.core.database import async_session_factory

        org_id = activity_org_id.get()
        if not org_id:
            return

        employee_id = activity_employee_id.get()
        async with async_session_factory() as session:
            await record_activity(
                session,
                UUID(org_id),
                event_type,
                summary,
                employee_id=UUID(employee_id) if employee_id else None,
                employee_name=activity_employee_name.get(),
                platform=activity_platform.get(),
                status=status,
                description=description,
                metadata=metadata,
                occurred_at=occurred_at,
            )
    except Exception:
        logger.debug("Failed to record contextual activity for %s", event_type, exc_info=True)


# ── CTE template (shared by feed + count queries) ──────────────────────────

_EVENT_CTES = """
WITH
agent_events AS (
    SELECT
        CONCAT('agent_job:', j.id::text) AS id,
        CASE
            WHEN j.job_type IN ('web_search', 'calculate', 'fetch_url')
                THEN 'tool_usage'
            WHEN j.job_type IN ('escalate_to_human', 'human_escalation')
                 OR j.status = 'awaiting_approval'
                THEN 'human_escalation'
            WHEN j.job_type IN ('remember', 'recall', 'search_knowledge_base',
                 'add_to_memory', 'query_memory', 'ingest_memory', 'search_memory')
                THEN 'memory_operation'
            ELSE 'agent_run'
        END AS event_type,
        COALESCE(
            CASE
                WHEN j.job_type = 'web_search' AND j.payload ? 'query'
                    THEN CONCAT('Web search: "', j.payload->>'query', '"')
                WHEN j.job_type = 'calculate' AND j.payload ? 'expression'
                    THEN CONCAT('Calculation: ', j.payload->>'expression')
                WHEN j.job_type = 'fetch_url' AND j.payload ? 'url'
                    THEN CONCAT('Fetched URL: ', j.payload->>'url')
                WHEN j.job_type = 'remember' AND j.payload ? 'content'
                    THEN CONCAT('Memory ingest: ', LEFT(j.payload->>'content', 80))
                WHEN j.job_type IN ('recall', 'search_knowledge_base', 'search_memory')
                     AND j.payload ? 'query'
                    THEN CONCAT('Memory search: "', j.payload->>'query', '"')
                WHEN j.status = 'awaiting_approval'
                    THEN CONCAT('Escalation awaiting approval from ', j.job_type)
                ELSE j.user_text
            END,
            j.job_type
        ) AS summary,
        jsonb_build_object(
            'job_type', j.job_type,
            'result_text', LEFT(COALESCE(j.result_text, ''), 500),
            'payload', j.payload,
            'error', j.error,
            'channel_id', j.channel_id,
            'thread_key', j.thread_key
        )::text AS description,
        j.employee_id,
        e.name AS employee_name,
        j.platform,
        j.status,
        jsonb_build_object(
            'job_type', j.job_type,
            'progress', j.progress,
            'error', j.error
        ) AS metadata,
        j.created_at AS occurred_at
    FROM agent_jobs j
    LEFT JOIN employees e ON e.id = j.employee_id
),
doc_events AS (
    SELECT
        CONCAT('document:', d.id::text) AS id,
        'document_upload' AS event_type,
        CONCAT('Uploaded ', d.filename, ' (', CASE
            WHEN d.size_bytes >= 1073741824 THEN CONCAT(ROUND(d.size_bytes::numeric / 1073741824, 1), ' GB')
            WHEN d.size_bytes >= 1048576 THEN CONCAT(ROUND(d.size_bytes::numeric / 1048576, 1), ' MB')
            WHEN d.size_bytes >= 1024 THEN CONCAT(ROUND(d.size_bytes::numeric / 1024, 1), ' KB')
            ELSE CONCAT(d.size_bytes::text, ' B')
        END, ')') AS summary,
        jsonb_build_object(
            'content_type', d.content_type,
            'size_bytes', d.size_bytes,
            'storage_backend', d.storage_backend
        )::text AS description,
        d.employee_id,
        e.name AS employee_name,
        NULL AS platform,
        d.status,
        jsonb_build_object(
            'filename', d.filename,
            'content_type', d.content_type,
            'size_bytes', d.size_bytes
        ) AS metadata,
        d.uploaded_at AS occurred_at
    FROM documents d
    LEFT JOIN employees e ON e.id = d.employee_id
),
emp_events AS (
    SELECT
        CONCAT('employee_created:', e.id::text) AS id,
        'employee_created' AS event_type,
        CONCAT('Employee "', e.name, '" created') AS summary,
        jsonb_build_object(
            'employee_type', e.employee_type,
            'role', e.role,
            'specialization', e.specialization
        )::text AS description,
        e.id AS employee_id,
        e.name AS employee_name,
        NULL AS platform,
        e.status,
        jsonb_build_object(
            'employee_type', e.employee_type,
            'role', e.role
        ) AS metadata,
        e.created_at AS occurred_at
    FROM employees e
    UNION ALL
    SELECT
        CONCAT('employee_updated:', e.id::text, ':', EXTRACT(EPOCH FROM e.updated_at)::bigint::text) AS id,
        'employee_updated' AS event_type,
        CASE
            WHEN e.status = 'active' THEN CONCAT('Employee "', e.name, '" activated')
            WHEN e.status = 'inactive' THEN CONCAT('Employee "', e.name, '" deactivated')
            WHEN e.status = 'suspended' THEN CONCAT('Employee "', e.name, '" suspended')
            ELSE CONCAT('Employee "', e.name, '" updated')
        END AS summary,
        jsonb_build_object(
            'employee_type', e.employee_type,
            'status', e.status,
            'role', e.role
        )::text AS description,
        e.id AS employee_id,
        e.name AS employee_name,
        NULL AS platform,
        e.status,
        jsonb_build_object(
            'employee_type', e.employee_type,
            'status', e.status
        ) AS metadata,
        e.updated_at AS occurred_at
    FROM employees e
    WHERE e.updated_at IS NOT NULL
),
recorded_events AS (
    SELECT
        CONCAT('recorded:', ae.id::text) AS id,
        ae.event_type,
        ae.summary,
        ae.description,
        ae.employee_id,
        ae.employee_name,
        ae.platform,
        ae.status,
        ae.metadata AS metadata,
        ae.occurred_at
    FROM activity_events ae
),
all_events AS (
    SELECT * FROM agent_events
    UNION ALL
    SELECT * FROM doc_events
    UNION ALL
    SELECT * FROM emp_events
    UNION ALL
    SELECT * FROM recorded_events
)
"""

# ── Shared WHERE clause builder ─────────────────────────────────────────────


def _build_org_and_filters(
    org_id: UUID,
    event_types: list[str] | None,
    employee_id: UUID | None,
    employee_type: str | None,
    q: str | None = None,
    *,  # start parameter placeholders
    date_from_label: str = "date_from",
    date_to_label: str = "date_to",
) -> str:
    """Build the WHERE clause for org-scoping and optional filters.

    Returns a SQL fragment that references named parameters:
      :org_id, :date_from, :date_to, :employee_id, :employee_type
    and a literal ARRAY[...] for event_types (safe — values are validated enum labels).
    """
    clauses = [
        "("
        # agent / employee events: employee belongs to the org
        "   (ae.employee_id IS NULL AND ae.id NOT LIKE 'document:%' AND ae.id NOT LIKE 'recorded:%')"
        "   OR (ae.employee_id IS NOT NULL"
        "       AND ae.employee_id IN (SELECT id FROM employees WHERE org_id = :org_id))"
        # document events: org_id matches directly via subquery
        "   OR (ae.id LIKE 'document:%'"
        "       AND (SELECT d2.org_id FROM documents d2"
        "            WHERE d2.id::text = REPLACE(ae.id, 'document:', '')) = :org_id)"
        # recorded events: org_id matches directly via subquery
        "   OR (ae.id LIKE 'recorded:%'"
        "       AND (SELECT ae2.org_id FROM activity_events ae2"
        "            WHERE ae2.id::text = REPLACE(ae.id, 'recorded:', '')) = :org_id)"
        ")",
        f"AND ae.occurred_at >= :{date_from_label}",
        f"AND ae.occurred_at <= :{date_to_label}",
    ]

    if event_types:
        # Only include values that match known event types (whitelist for safety)
        safe_types = [et for et in event_types if et in _ALLOWED_EVENT_TYPES]
        if safe_types:
            literals = ", ".join(f"'{et}'" for et in safe_types)
            clauses.append(f"AND ae.event_type = ANY(ARRAY[{literals}])")

    if employee_id is not None:
        clauses.append("AND ae.employee_id = :employee_id")

    if employee_type:
        clauses.append(
            "AND ae.employee_id IN ("
            "SELECT id FROM employees WHERE org_id = :org_id AND employee_type = :employee_type"
            ")"
        )

    if q:
        clauses.append(
            "AND (ae.summary ILIKE :q OR COALESCE(ae.description, '') ILIKE :q)"
        )

    return "\n    ".join(clauses)


# ── Public API ──────────────────────────────────────────────────────────────


async def get_activity_feed(
    db: AsyncSession,
    org_id: UUID,
    *,
    event_types: list[str] | None = None,
    employee_id: UUID | None = None,
    employee_type: str | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = 0,
    limit: int = _PAGE_SIZE,
) -> ActivityFeedResponse:
    """Return a unified activity feed for the organization."""
    if date_to is None:
        date_to = datetime.now(timezone.utc)
    if date_from is None:
        date_from = date_to - timedelta(days=90)

    where_clause = _build_org_and_filters(
        org_id, event_types, employee_id, employee_type, q,
        date_from_label="df", date_to_label="dt",
    )

    query_sql = (
        _EVENT_CTES
        + f"""
    SELECT ae.*
    FROM all_events ae
    WHERE {where_clause}
    ORDER BY ae.occurred_at DESC
    OFFSET :offset
    LIMIT :limit
    """
    )

    count_sql = (
        _EVENT_CTES
        + f"""
    SELECT COUNT(*) AS total
    FROM all_events ae
    WHERE {where_clause}
    """
    )

    params: dict = {
        "org_id": org_id,
        "df": date_from,
        "dt": date_to,
        "offset": offset,
        "limit": limit,
    }
    if employee_id is not None:
        params["employee_id"] = employee_id
    if employee_type:
        params["employee_type"] = employee_type
    if q:
        params["q"] = f"%{q}%"

    rows_result = await db.execute(text(query_sql), params)
    rows = rows_result.fetchall()

    count_params = {k: v for k, v in params.items() if k in ("org_id", "df", "dt", "employee_id", "q")}
    count_result = await db.execute(text(count_sql), count_params)
    total = count_result.scalar() or 0

    events = [
        ActivityEventResponse(
            id=row.id,
            event_type=row.event_type,
            summary=row.summary or "",
            description=row.description,
            employee_id=row.employee_id,
            employee_name=row.employee_name,
            platform=row.platform,
            status=row.status,
            metadata=row.metadata,
            occurred_at=row.occurred_at,
        )
        for row in rows
        if row.id is not None
    ]

    next_offset = offset + limit if offset + limit < total else None
    return ActivityFeedResponse(events=events, total=total, next_offset=next_offset)


async def get_activity_stats(
    db: AsyncSession,
    org_id: UUID,
) -> ActivityStatsResponse:
    """Return today's activity counts grouped by type for the organization."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_end = today_start + timedelta(days=1)

    async def _count(query: str, **params) -> int:
        result = await db.execute(text(query), params)
        val = result.scalar()
        return val or 0

    agent_count = await _count(
        """
        SELECT COUNT(*) FROM agent_jobs j
        WHERE j.created_at >= :today_start
          AND j.created_at < :today_end
          AND j.employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    doc_count = await _count(
        """
        SELECT COUNT(*) FROM documents d
        WHERE d.uploaded_at >= :today_start
          AND d.uploaded_at < :today_end
          AND d.org_id = :org_id
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    emp_count = await _count(
        """
        SELECT COUNT(*) FROM employees e
        WHERE ((e.created_at >= :today_start AND e.created_at < :today_end)
            OR (e.updated_at >= :today_start AND e.updated_at < :today_end))
          AND e.org_id = :org_id
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    tool_count = await _count(
        """
        SELECT COUNT(*) FROM agent_jobs j
        WHERE j.job_type IN ('web_search', 'calculate', 'fetch_url')
          AND j.created_at >= :today_start
          AND j.created_at < :today_end
          AND j.employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    human_count = await _count(
        """
        SELECT COUNT(*) FROM agent_jobs j
        WHERE (j.job_type IN ('escalate_to_human', 'human_escalation')
               OR j.status = 'awaiting_approval')
          AND j.created_at >= :today_start
          AND j.created_at < :today_end
          AND j.employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    memory_count = await _count(
        """
        SELECT COUNT(*) FROM agent_jobs j
        WHERE j.job_type IN ('remember', 'recall', 'search_knowledge_base',
                             'add_to_memory', 'query_memory', 'ingest_memory',
                             'search_memory')
          AND j.created_at >= :today_start
          AND j.created_at < :today_end
          AND j.employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
        """,
        today_start=today_start,
        today_end=today_end,
        org_id=org_id,
    )

    return ActivityStatsResponse(
        total_today=agent_count + doc_count + emp_count,
        agent_runs=agent_count,
        document_uploads=doc_count,
        employee_events=emp_count,
        tool_usages=tool_count,
        human_escalations=human_count,
        memory_operations=memory_count,
    )
