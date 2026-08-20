"""Async queue operations for the agent job table.

Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` for lock-free dequeue and per-thread
serialization — a pending job is only claimed when no other job for the same
``thread_key`` is already running or awaiting approval.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.jobs.models import AgentJob

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cancel-intent keyword patterns (Phase 3 — lightweight pre-graph fast path)
# ---------------------------------------------------------------------------

# Only match unambiguous, terse cancel commands.  Avoid false positives like
# "cancel my subscription", "stop by my desk", "how do I cancel?"
_CANCEL_EXACT = frozenset({
    "cancel", "stop", "abort", "nvm", "nevermind", "never mind",
    "cancel that", "stop that", "abort that", "forget it",
    "cancel it", "stop it", "cancel this", "stop this",
})

_CANCEL_RE = re.compile(
    r"^(cancel|stop|abort|never\s*mind|nvm|forget\s+it)\b[.!?,;:]*$",
    re.IGNORECASE,
)


def is_cancel_intent(text: str) -> bool:
    """Return ``True`` if *text* is unambiguously a cancel / abort command.

    Designed to be called **before** the agent graph so bots can cancel
    background jobs without an LLM round-trip.
    """
    cleaned = text.strip().lower().rstrip(".!?,;:'\"")
    if not cleaned:
        return False
    if cleaned in _CANCEL_EXACT:
        return True
    return bool(_CANCEL_RE.match(cleaned))


async def enqueue_job(
    db: AsyncSession,
    *,
    employee_id: UUID,
    platform: str,
    channel_id: str,
    thread_key: str,
    job_type: str,
    payload: dict | None = None,
    user_text: str | None = None,
) -> AgentJob:
    """Insert a new job row and return it."""
    job = AgentJob(
        employee_id=employee_id,
        platform=platform,
        channel_id=channel_id,
        thread_key=thread_key,
        job_type=job_type,
        payload=payload,
        user_text=user_text,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.debug("Enqueued job %s (type=%s, thread=%s)", job.id, job_type, thread_key)
    return job


async def claim_next_job(db: AsyncSession, lease_owner: str | None = None) -> AgentJob | None:
    """Claim the oldest pending job whose thread is not already busy.

    A thread is "busy" if any job with the same ``thread_key`` has status
    ``running`` or ``awaiting_approval``.  This provides per-thread FIFO
    serialization for background work (Phase 3 concurrency control).

    Uses ``FOR UPDATE SKIP LOCKED`` so concurrent workers never block on each
    other.
    """
    busy_threads = (
        select(AgentJob.thread_key)
        .where(AgentJob.status.in_(["running", "awaiting_approval"]))
    )

    stmt = (
        select(AgentJob)
        .where(
            AgentJob.status == "pending",
            AgentJob.job_type != "cronjob",
            or_(AgentJob.available_at.is_(None), AgentJob.available_at <= datetime.now(UTC)),
            AgentJob.thread_key.not_in(busy_threads),
        )
        .order_by(AgentJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        return None

    # Mark as running immediately inside the same locked row
    job.status = "running"
    job.started_at = datetime.now(UTC)
    job.lease_owner = lease_owner
    job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=12)
    await db.commit()
    await db.refresh(job)

    logger.info("Claimed job %s (type=%s, thread=%s)", job.id, job.job_type, job.thread_key)
    return job


async def get_job(db: AsyncSession, job_id: UUID) -> AgentJob | None:
    """Return a single job by id, or ``None``."""
    result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
    return result.scalar_one_or_none()


async def get_active_jobs_for_thread(
    db: AsyncSession, thread_key: str
) -> list[AgentJob]:
    """Return all jobs for *thread_key* that are still active.

    Active means ``pending``, ``running``, or ``awaiting_approval``.
    """
    result = await db.execute(
        select(AgentJob)
        .where(
            AgentJob.thread_key == thread_key,
            AgentJob.status.in_(["pending", "running", "awaiting_approval"]),
        )
        .order_by(AgentJob.created_at)
    )
    return list(result.scalars().all())


async def cancel_active_jobs_for_thread(
    db: AsyncSession, thread_key: str
) -> list[AgentJob]:
    """Cancel every active job for *thread_key*.

    Marks each job ``cancelled`` in the database and attempts to cancel the
    corresponding in-flight asyncio task via the active worker singleton.

    Returns the list of jobs that were cancelled (may be empty).
    """
    from app.agent.jobs.worker import get_active_worker

    result = await db.execute(
        select(AgentJob)
        .where(
            AgentJob.thread_key == thread_key,
            AgentJob.status.in_(["pending", "running", "awaiting_approval"]),
        )
    )
    jobs = list(result.scalars().all())

    if not jobs:
        return []

    now = datetime.now(UTC)
    worker = get_active_worker()

    for job in jobs:
        job.status = "cancelled"
        job.error = "Cancelled by user request (keyword fast-path)"
        job.finished_at = now

        # Cancel in-flight asyncio task
        if worker is not None:
            await worker.cancel_job(str(job.id))

    await db.commit()
    for job in jobs:
        await db.refresh(job)

    logger.info(
        "Cancelled %d active job(s) for thread %s (keyword fast-path)",
        len(jobs), thread_key,
    )
    return jobs
