"""Job runner — dispatches a claimed :class:`AgentJob` to the right handler.

In Phase 1 the registry is a stub.  Phase 2 will register real handlers for
``analyze_document``, ``search_knowledge_base``, etc.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.agent.jobs.models import AgentJob

logger = logging.getLogger(__name__)

#: Handler signature: ``async (job: AgentJob) -> None``.
#: The handler is responsible for updating ``job.progress``, ``job.result_text``,
#: ``job.status``, and posting the final result to Slack/Discord.
JobHandler = Callable[[AgentJob], Awaitable[None]]

_registry: dict[str, JobHandler] = {}


def register_default_handlers() -> None:
    """Register durable handlers without importing them at module load time."""
    from app.schedules.executor import run_scheduled_employee_job

    register_handler("scheduled_employee_run", run_scheduled_employee_job)


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register a handler for *job_type*."""
    if job_type in _registry:
        logger.warning("Handler for job_type=%r is being overwritten", job_type)
    _registry[job_type] = handler
    logger.info("Registered handler for job_type=%r", job_type)


async def run_job(job: AgentJob) -> None:
    """Dispatch *job* to the registered handler.

    If no handler is registered the job is marked ``failed`` with an
    appropriate error message.
    """
    handler = _registry.get(job.job_type)
    if handler is None:
        logger.error(
            "No handler registered for job_type=%r (job %s)", job.job_type, job.id,
        )
        # Mark failed — the caller (worker) does its own DB session management,
        # so we assume the worker will persist the error.
        job.status = "failed"
        job.error = f"No handler registered for job_type={job.job_type!r}"
        job.finished_at = None  # set by worker
        return

    logger.info("Running job %s (type=%s)", job.id, job.job_type)
    try:
        await handler(job)
    except Exception:
        logger.exception("Handler for job_type=%r failed (job %s)", job.job_type, job.id)
        job.status = "failed"
        job.error = f"Handler raised: {job.error}" if job.error else "Handler raised an exception"
        # finished_at is set by the worker after run_job returns
