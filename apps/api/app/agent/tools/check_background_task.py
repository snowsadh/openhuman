"""Tool for checking the status of background agent jobs.

Agents call this to answer user questions like "how's that going?" or
"is the PDF analysis done yet?" without blocking the conversation.
"""

from __future__ import annotations

import json
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.jobs.queue import get_active_jobs_for_thread, get_job


@tool
async def check_background_task(
    job_id: str = "",
    config: RunnableConfig = None,
) -> str:
    """Check the status of a background task.

    If *job_id* is provided, returns detailed status for that single job
    (including progress and any partial results).

    If *job_id* is empty or omitted, returns a summary of all active
    (pending / running / awaiting_approval) jobs for this conversation thread.

    Use this tool whenever the user asks about the progress or status of
    something you previously started in the background — for example, "how's
    that document analysis going?" or "is the search done yet?".
    """
    configurable = config.get("configurable", {}) if config else {}
    db = configurable.get("db")
    thread_key = configurable.get("thread_id", "")

    if db is None:
        return json.dumps({"error": "No database session available in agent config."})

    # -- Single-job lookup -------------------------------------------------
    if job_id:
        try:
            parsed_id = UUID(job_id)
        except (ValueError, AttributeError):
            return json.dumps({"error": f"Invalid job_id: {job_id!r}"})

        job = await get_job(db, parsed_id)
        if job is None:
            return json.dumps({"error": f"No task found with job_id={job_id!r}."})

        return json.dumps({
            "job_id": str(job.id),
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "result": job.result_text,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }, default=str)

    # -- List all active jobs for this thread -------------------------------
    if not thread_key:
        return json.dumps({"error": "No thread_id available to look up background tasks."})

    jobs = await get_active_jobs_for_thread(db, thread_key)
    if not jobs:
        return json.dumps({
        "message": "No active background tasks in this conversation.",
        "jobs": [],
    })

    return json.dumps({
        "jobs": [
            {
                "job_id": str(j.id),
                "job_type": j.job_type,
                "status": j.status,
                "progress": j.progress,
            }
            for j in jobs
        ],
    }, default=str)
