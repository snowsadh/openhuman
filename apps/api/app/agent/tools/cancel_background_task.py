"""Tool for cancelling a running background agent job.

Agents call this when the user expresses cancel intent — e.g. "cancel that
analysis", "stop", "never mind about the PDF".
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.jobs.queue import get_job
from app.agent.jobs.worker import get_active_worker

logger = logging.getLogger(__name__)


@tool
async def cancel_background_task(
    job_id: str = "",
    config: RunnableConfig = None,
) -> str:
    """Cancel a running or pending background task.

    Provide the *job_id* of the task to cancel.  If *job_id* is empty the
    tool will look for any active (pending / running) job in the current
    conversation thread and cancel the most recent one.

    Use this tool when the user says things like "cancel", "stop that",
    "never mind", or otherwise indicates they want to abort a background
    operation you started earlier.
    """
    configurable = config.get("configurable", {}) if config else {}
    db = configurable.get("db")
    thread_key = configurable.get("thread_id", "")

    if db is None:
        return json.dumps({"error": "No database session available in agent config."})

    # -- Resolve the target job --------------------------------------------
    target_job = None

    if job_id:
        try:
            parsed_id = UUID(job_id)
        except (ValueError, AttributeError):
            return json.dumps({"error": f"Invalid job_id: {job_id!r}"})
        target_job = await get_job(db, parsed_id)
        if target_job is None:
            return json.dumps({"error": f"No task found with job_id={job_id!r}."})
    elif thread_key:
        from app.agent.jobs.queue import get_active_jobs_for_thread

        active = await get_active_jobs_for_thread(db, thread_key)
        # Cancel the most recently created active job
        if active:
            target_job = active[-1]

    if target_job is None:
        return json.dumps({"message": "No active background task to cancel."})

    # -- Mark cancelled in the database ------------------------------------
    if target_job.status in ("pending", "running", "awaiting_approval"):
        target_job.status = "cancelled"
        target_job.error = "Cancelled by user request"
        target_job.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(target_job)

        # -- Cancel the running asyncio Task if it's in-flight -------------
        worker = get_active_worker()
        if worker is not None:
            cancelled_task = await worker.cancel_job(str(target_job.id))
            if cancelled_task:
                logger.info(
                    "Cancelled in-flight asyncio task for job %s", target_job.id,
                )

        return json.dumps({
            "cancelled": True,
            "job_id": str(target_job.id),
            "job_type": target_job.job_type,
            "message": f"Background task '{target_job.job_type}' has been cancelled.",
        })

    return json.dumps({
        "cancelled": False,
        "job_id": str(target_job.id),
        "status": target_job.status,
        "message": f"Task is already in terminal state '{target_job.status}'.",
    })
