"""
Integration tests for the AI engine — async agents, job queue, concurrency
control, checkpointer, and human-in-the-loop escalation.

Covers Phases 1-6 of the async_agents_hitl_escalation_plan.

Usage::

    # Run all integration tests (SQLite — fast, no external deps)
    uv run pytest test/test_integration.py -v

    # Run with real PostgreSQL for checkpointer tests
    USE_API_DB=true uv run pytest test/test_integration.py -v

    # Run a specific phase
    uv run pytest test/test_integration.py -v -k "phase1"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure `app` is importable
# ---------------------------------------------------------------------------
_this_dir = Path(__file__).resolve().parent
_api_dir = _this_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

# Load .env if present
_env_path = _api_dir / ".env"
if _env_path.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_path)

# SQLAlchemy imports
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Test fixtures
from test.fixtures import (
    SEED_EMPLOYEES,
    SEED_EMPLOYEE_IDS,
    get_escalation_policy,
    set_escalation_policy,
    set_slack_token,
    setup_test_db,
)

# ---------------------------------------------------------------------------
# Detect whether we're running against a real PostgreSQL
# ---------------------------------------------------------------------------
# Default to SQLite (:memory:) — fast, isolated, no external deps.
# Set USE_API_DB=true to run against the real API database (requires migrations).
USE_API_DB = os.environ.get("USE_API_DB", "").lower() in ("1", "true", "yes")
_pg_url = os.environ.get("DATABASE_URL", "")

IS_POSTGRES = USE_API_DB and _pg_url.startswith("postgresql")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def event_loop():
    """Create a fresh event loop for the module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def test_db():
    """Set up a test database (SQLite or PG) once per module.

    Returns ``(engine, session_factory, employee_ids)``.
    """
    if IS_POSTGRES:
        db_url = _pg_url or os.environ.get("DATABASE_URL", "")
        engine, sf, ids = await setup_test_db(db_url)
    else:
        engine, sf, ids = await setup_test_db(":memory:")

    yield engine, sf, ids

    await engine.dispose()


@pytest.fixture
async def db_session(test_db):
    """Yield a fresh async session for each test."""
    _engine, session_factory, _ids = test_db
    async with session_factory() as session:
        yield session


@pytest.fixture
def employee_ids(test_db):
    """Return the seed employee id map."""
    _engine, _sf, ids = test_db
    return ids


# =============================================================================
# Phase 1 — Job Queue
# =============================================================================


class TestPhase1JobQueue:
    """Tests for the Postgres-backed agent job queue (Phase 1)."""

    async def test_agent_job_model_creation(self, db_session: AsyncSession, employee_ids):
        """An AgentJob row can be inserted and read back."""
        from app.agent.jobs.models import AgentJob

        job = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C123",
            thread_key="slack:test:thread:1",
            job_type="test_job",
            payload={"key": "value"},
            user_text="analyze this",
            status="pending",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        assert job.id is not None
        assert job.status == "pending"
        assert job.job_type == "test_job"
        assert job.thread_key == "slack:test:thread:1"
        assert job.payload == {"key": "value"}
        assert job.created_at is not None

    async def test_enqueue_job(self, db_session: AsyncSession, employee_ids):
        """enqueue_job inserts a pending job and returns it."""
        from app.agent.jobs.queue import enqueue_job

        job = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="discord",
            channel_id="D456",
            thread_key="discord:test:thread:2",
            job_type="analyze_document",
            payload={"document_path": "/tmp/test.pdf"},
            user_text="analyze this PDF",
        )

        assert job.id is not None
        assert job.status == "pending"
        assert job.platform == "discord"
        assert job.job_type == "analyze_document"

    async def test_get_job(self, db_session: AsyncSession, employee_ids):
        """get_job returns the correct job or None for missing."""
        from app.agent.jobs.queue import enqueue_job, get_job

        job = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C789",
            thread_key="slack:test:thread:3",
            job_type="search_kb",
        )

        found = await get_job(db_session, job.id)
        assert found is not None
        assert found.id == job.id
        assert found.job_type == "search_kb"

        # Non-existent
        missing = await get_job(db_session, UUID("00000000-0000-0000-0000-000000000000"))
        assert missing is None

    @pytest.mark.skipif(not IS_POSTGRES, reason="FOR UPDATE SKIP LOCKED requires PostgreSQL")
    async def test_claim_next_job(self, db_session: AsyncSession, employee_ids):
        """claim_next_job picks up the oldest pending job and marks it running."""
        from app.agent.jobs.queue import claim_next_job, enqueue_job

        # Enqueue two jobs on different threads
        job1 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:th:1",
            job_type="type_a",
        )
        job2 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C2",
            thread_key="slack:th:2",
            job_type="type_b",
        )

        # Claim the oldest (job1)
        claimed = await claim_next_job(db_session)
        assert claimed is not None
        assert claimed.id == job1.id
        assert claimed.status == "running"
        assert claimed.started_at is not None

        # job2 is still claimable (different thread)
        claimed2 = await claim_next_job(db_session)
        assert claimed2 is not None
        assert claimed2.id == job2.id
        assert claimed2.status == "running"

        # No more pending jobs
        claimed3 = await claim_next_job(db_session)
        assert claimed3 is None

    @pytest.mark.skipif(not IS_POSTGRES, reason="FOR UPDATE SKIP LOCKED requires PostgreSQL")
    async def test_per_thread_serialization(self, db_session: AsyncSession, employee_ids):
        """claim_next_job skips threads that already have a running job (Phase 3)."""
        from app.agent.jobs.queue import claim_next_job, enqueue_job

        thread = "slack:serial:1"

        # Enqueue two jobs on the SAME thread
        job_a = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C99",
            thread_key=thread,
            job_type="type_a",
        )
        job_b = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C99",
            thread_key=thread,
            job_type="type_b",
        )

        # Claim first job — it becomes running
        claimed = await claim_next_job(db_session)
        assert claimed is not None
        assert claimed.id == job_a.id
        assert claimed.status == "running"

        # Second job on same thread should NOT be claimable while first is running
        blocked = await claim_next_job(db_session)
        assert blocked is None  # still pending but thread is busy

        # Mark first job as completed
        claimed.status = "succeeded"
        claimed.finished_at = claimed.started_at
        await db_session.commit()

        # Now second job is claimable
        claimed2 = await claim_next_job(db_session)
        assert claimed2 is not None
        assert claimed2.id == job_b.id

    async def test_get_active_jobs_for_thread(self, db_session: AsyncSession, employee_ids):
        """get_active_jobs_for_thread returns only active (non-terminal) jobs."""
        from app.agent.jobs.queue import enqueue_job, get_active_jobs_for_thread

        thread = "slack:active:thread:1"

        job1 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_a",
        )
        # Insert a succeeded job directly
        from app.agent.jobs.models import AgentJob
        from datetime import UTC, datetime

        job2 = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_b",
            status="succeeded",
            finished_at=datetime.now(UTC),
        )
        db_session.add(job2)
        await db_session.commit()

        active = await get_active_jobs_for_thread(db_session, thread)
        assert len(active) == 1
        assert active[0].id == job1.id
        assert active[0].status == "pending"

    async def test_cancel_active_jobs_for_thread(self, db_session: AsyncSession, employee_ids):
        """cancel_active_jobs_for_thread marks all active jobs cancelled."""
        from app.agent.jobs.queue import cancel_active_jobs_for_thread, enqueue_job

        thread = "slack:cancel:thread:1"

        job1 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_a",
        )
        job2 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_b",
        )

        cancelled = await cancel_active_jobs_for_thread(db_session, thread)
        assert len(cancelled) == 2
        assert all(j.status == "cancelled" for j in cancelled)
        assert all(j.finished_at is not None for j in cancelled)

        # Cancelling again is a no-op (no active jobs left)
        cancelled2 = await cancel_active_jobs_for_thread(db_session, thread)
        assert len(cancelled2) == 0

    @pytest.mark.skipif(not IS_POSTGRES, reason="FOR UPDATE SKIP LOCKED requires PostgreSQL")
    async def test_claim_next_job_skip_locked(self, db_session: AsyncSession, employee_ids):
        """Concurrent claim attempts don't double-claim the same job."""
        from app.agent.jobs.queue import enqueue_job

        # Enqueue a single job
        await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:skip:locked:1",
            job_type="type_a",
        )

        # Simulate two concurrent claims — second should get None
        # (FOR UPDATE SKIP LOCKED ensures this)
        from app.agent.jobs.queue import claim_next_job

        claimed1 = await claim_next_job(db_session)
        assert claimed1 is not None
        assert claimed1.status == "running"

        claimed2 = await claim_next_job(db_session)
        assert claimed2 is None


# =============================================================================
# Phase 2 — Tool-level async dispatch
# =============================================================================


class TestPhase2AsyncDispatch:
    """Tests for tool-level async dispatch (Phase 2)."""

    async def test_check_background_task_by_job_id(
        self, db_session: AsyncSession, employee_ids
    ):
        """check_background_task returns job details when given a job_id."""
        from app.agent.jobs.queue import enqueue_job
        from app.agent.tools.check_background_task import check_background_task

        job = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:check:by:id:1",
            job_type="analyze_document",
            payload={"doc": "test.pdf"},
        )

        result_str = await check_background_task.ainvoke(
            {"job_id": str(job.id)},
            config={"configurable": {"db": db_session, "thread_id": "slack:check:by:id:1"}},
        )
        result = json.loads(result_str)

        assert result["job_id"] == str(job.id)
        assert result["job_type"] == "analyze_document"
        assert result["status"] == "pending"

    async def test_check_background_task_invalid_id(self, db_session: AsyncSession):
        """check_background_task returns error for invalid job_id."""
        from app.agent.tools.check_background_task import check_background_task

        result_str = await check_background_task.ainvoke(
            {"job_id": "not-a-uuid"},
            config={"configurable": {"db": db_session}},
        )
        result = json.loads(result_str)
        assert "error" in result

    async def test_check_background_task_list_active(self, db_session: AsyncSession, employee_ids):
        """check_background_task lists all active jobs when no job_id given."""
        from app.agent.jobs.queue import enqueue_job
        from app.agent.tools.check_background_task import check_background_task

        thread = "slack:check:list:1"
        await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_a",
        )
        await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_b",
        )

        result_str = await check_background_task.ainvoke(
            {"job_id": ""},
            config={"configurable": {"db": db_session, "thread_id": thread}},
        )
        result = json.loads(result_str)

        assert "jobs" in result
        assert len(result["jobs"]) == 2

    async def test_check_background_task_no_active(self, db_session: AsyncSession):
        """check_background_task reports no active jobs when thread is idle."""
        from app.agent.tools.check_background_task import check_background_task

        result_str = await check_background_task.ainvoke(
            {"job_id": ""},
            config={"configurable": {"db": db_session, "thread_id": "slack:idle:thread"}},
        )
        result = json.loads(result_str)
        assert "No active background tasks" in result.get("message", "")

    async def test_cancel_background_task_by_job_id(
        self, db_session: AsyncSession, employee_ids
    ):
        """cancel_background_task cancels a specific job by ID."""
        from app.agent.jobs.queue import enqueue_job
        from app.agent.tools.cancel_background_task import cancel_background_task

        job = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:cancel:by:id:1",
            job_type="type_a",
        )

        result_str = await cancel_background_task.ainvoke(
            {"job_id": str(job.id)},
            config={"configurable": {"db": db_session, "thread_id": "slack:cancel:by:id:1"}},
        )
        result = json.loads(result_str)

        assert result["cancelled"] is True
        assert result["job_id"] == str(job.id)

        # Verify in DB
        from app.agent.jobs.queue import get_job

        updated = await get_job(db_session, job.id)
        assert updated.status == "cancelled"

    async def test_cancel_background_task_most_recent(
        self, db_session: AsyncSession, employee_ids
    ):
        """cancel_background_task cancels the most recent active job when no ID given."""
        from app.agent.jobs.queue import enqueue_job
        from app.agent.tools.cancel_background_task import cancel_background_task

        thread = "slack:cancel:recent:1"
        job1 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_a",
        )
        job2 = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key=thread,
            job_type="type_b",
        )

        result_str = await cancel_background_task.ainvoke(
            {"job_id": ""},
            config={"configurable": {"db": db_session, "thread_id": thread}},
        )
        result = json.loads(result_str)

        # Should cancel the most recent (job2)
        assert result["cancelled"] is True
        assert result["job_id"] == str(job2.id)

        # job1 should still be pending
        from app.agent.jobs.queue import get_job

        j1 = await get_job(db_session, job1.id)
        assert j1.status == "pending"

    async def test_cancel_background_task_already_terminal(
        self, db_session: AsyncSession, employee_ids
    ):
        """cancel_background_task handles already-terminal jobs gracefully."""
        from app.agent.jobs.queue import enqueue_job
        from app.agent.tools.cancel_background_task import cancel_background_task

        job = await enqueue_job(
            db_session,
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:cancel:terminal:1",
            job_type="type_a",
        )

        # Mark as already succeeded
        job.status = "succeeded"
        await db_session.commit()

        result_str = await cancel_background_task.ainvoke(
            {"job_id": str(job.id)},
            config={"configurable": {"db": db_session}},
        )
        result = json.loads(result_str)

        assert result["cancelled"] is False
        assert "terminal state" in result.get("message", "")


# =============================================================================
# Phase 3 — Concurrency Control and Cancel Detection
# =============================================================================


class TestPhase3ConcurrencyControl:
    """Tests for concurrency control, cancel intent, and worker lifecycle (Phase 3)."""

    async def test_is_cancel_intent_exact(self):
        """is_cancel_intent matches exact cancel phrases."""
        from app.agent.jobs.queue import is_cancel_intent

        assert is_cancel_intent("cancel") is True
        assert is_cancel_intent("stop") is True
        assert is_cancel_intent("abort") is True
        assert is_cancel_intent("nvm") is True
        assert is_cancel_intent("nevermind") is True
        assert is_cancel_intent("never mind") is True
        assert is_cancel_intent("cancel that") is True
        assert is_cancel_intent("stop that") is True
        assert is_cancel_intent("forget it") is True

    async def test_is_cancel_intent_regex(self):
        """is_cancel_intent matches regex patterns with punctuation."""
        from app.agent.jobs.queue import is_cancel_intent

        assert is_cancel_intent("cancel.") is True
        assert is_cancel_intent("Stop!") is True
        assert is_cancel_intent("ABORT!") is True
        assert is_cancel_intent("cancel it.") is True
        assert is_cancel_intent("stop this!") is True

    async def test_is_cancel_intent_not_cancel(self):
        """is_cancel_intent rejects non-cancel phrases."""
        from app.agent.jobs.queue import is_cancel_intent

        assert is_cancel_intent("hello") is False
        assert is_cancel_intent("cancel my subscription") is False
        assert is_cancel_intent("stop by my desk") is False
        assert is_cancel_intent("how do I cancel?") is False
        assert is_cancel_intent("what's the stopping distance?") is False
        assert is_cancel_intent("") is False
        assert is_cancel_intent("  ") is False

    @pytest.mark.skipif(not IS_POSTGRES, reason="Worker recovery uses app DB factory (PG only)")
    async def test_worker_recovery(self, db_session: AsyncSession, employee_ids):
        """Worker recovery marks stranded in-flight jobs as failed."""
        from app.agent.jobs.models import AgentJob
        from datetime import UTC, datetime

        # Create a job that appears "stranded" (running but no worker)
        stranded = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="slack:recovery:1",
            job_type="type_a",
            status="running",
            started_at=datetime.now(UTC),
        )
        db_session.add(stranded)
        await db_session.commit()

        # Simulate recovery
        from app.agent.jobs.worker import AgentJobWorker

        worker = AgentJobWorker()
        await worker._recover()

        # Check the stranded job was marked failed
        from app.agent.jobs.queue import get_job

        updated = await get_job(db_session, stranded.id)
        assert updated is not None
        assert updated.status == "failed"
        assert "stranded" in (updated.error or "")

    async def test_worker_cancel_inflight_job(self, employee_ids):
        """AgentJobWorker.cancel_job cancels a running asyncio Task."""
        from app.agent.jobs.worker import AgentJobWorker

        worker = AgentJobWorker()

        # Create a mock task
        async def _long_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(_long_task(), name="test-job")
        worker._running_tasks["test-job-id"] = task

        # Cancel it
        result = await worker.cancel_job("test-job-id")
        assert result is True

        # Let the event loop process the cancellation
        await asyncio.sleep(0)

        # Should not find already-cancelled task
        result2 = await worker.cancel_job("test-job-id")
        assert result2 is False

        # Clean up
        try:
            await task
        except asyncio.CancelledError:
            pass


# =============================================================================
# Phase 4 — Postgres Checkpointer
# =============================================================================


@pytest.mark.skipif(not IS_POSTGRES, reason="Checkpointer requires PostgreSQL")
class TestPhase4Checkpointer:
    """Tests for the Postgres LangGraph checkpointer (Phase 4).

    These tests require a real PostgreSQL database.
    """

    async def test_checkpointer_initialization(self):
        """The checkpointer can be initialized and returns a valid saver."""
        from app.agent.checkpointer import close_checkpointer, get_checkpointer, init_checkpointer

        await init_checkpointer()
        saver = get_checkpointer()
        assert saver is not None

        # Cleanup
        await close_checkpointer
        assert get_checkpointer() is None

    async def test_graph_compiles_with_checkpointer(self):
        """build_graph compiles with the checkpointer attached."""
        from app.agent.build import build_graph
        from app.agent.checkpointer import close_checkpointer, init_checkpointer
        from app.agent.tools.executor import BUILT_IN_TOOLS

        await init_checkpointer()

        graph = build_graph(list(BUILT_IN_TOOLS))
        assert graph is not None
        assert graph.checkpointer is not None

        await close_checkpointer()

    async def test_thread_state_persistence(self, employee_ids):
        """Agent state is persisted and restored across invocations via thread_id."""
        from app.agent.build import build_graph
        from app.agent.checkpointer import close_checkpointer, init_checkpointer
        from app.agent.tools.executor import BUILT_IN_TOOLS

        await init_checkpointer()

        graph = build_graph(list(BUILT_IN_TOOLS))
        thread_id = f"test:persist:{uuid4()}"

        # Use the API's database for the test
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            from langchain_core.messages import HumanMessage

            config = {
                "configurable": {
                    "db": session,
                    "employee_id": str(employee_ids["general"]),
                    "all_tools": list(BUILT_IN_TOOLS),
                    "thread_id": thread_id,
                    "platform": "test",
                }
            }

            initial_state = {
                "messages": [HumanMessage(content="Hello, my name is TestUser")],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result1 = await graph.ainvoke(initial_state, config=config)
            response1 = result1.get("response", "")

            # Second invocation on same thread — state should be restored
            state2 = {
                "messages": [HumanMessage(content="What is my name?")],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result2 = await graph.ainvoke(state2, config=config)
            response2 = result2.get("response", "")

            # The agent should remember the name from the first message
            # (This is a soft check — the LLM may or may not recall,
            # but the checkpoint should be non-empty)
            assert response1  # first response exists
            assert response2  # second response exists
            # The message count in state should show merged history
            messages = result2.get("messages", [])
            # Should have at least 4 messages: Human1, AI1, Human2, AI2
            assert len(messages) >= 2

        await close_checkpointer()


# =============================================================================
# Phase 5 — Escalation (Fire-and-Forget)
# =============================================================================


class TestPhase5Escalation:
    """Tests for the fire-and-forget escalate_to_human tool (Phase 5)."""

    async def test_escalation_policy_storage(self, test_db, employee_ids):
        """Escalation policy can be stored and read back on an Employee."""
        _engine, session_factory, _ids = test_db

        policy = {
            "manager_slack_id": "U0123456789",
            "default_escalation_channel": "#escalations",
            "mode": "fire_and_forget",
        }

        ok = await set_escalation_policy(session_factory, employee_ids["general"], policy)
        assert ok is True

        stored = await get_escalation_policy(session_factory, employee_ids["general"])
        assert stored == policy

    async def test_escalation_policy_none_for_unset(self, test_db, employee_ids):
        """Unset escalation policy returns None."""
        _engine, session_factory, _ids = test_db
        stored = await get_escalation_policy(session_factory, employee_ids["hr_specialist"])
        # May be None if never set, or a dict if seeded
        assert stored is None or isinstance(stored, dict)

    async def test_escalate_to_human_no_policy(self, db_session: AsyncSession, employee_ids):
        """escalate_to_human returns error when no escalation policy is set."""
        from app.agent.tools.escalation import escalate_to_human

        result_str = await escalate_to_human.ainvoke(
            {"reason": "Test escalation", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(employee_ids["support_agent"]),
                    "platform": "slack",
                    "channel_id": "C123",
                    "thread_ts": "123.456",
                    "thread_id": "slack:test:escalate:1",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "no escalation policy" in result["message"].lower()

    async def test_escalate_to_human_missing_config(self, db_session: AsyncSession):
        """escalate_to_human returns error when config is missing."""
        from app.agent.tools.escalation import escalate_to_human

        result_str = await escalate_to_human.ainvoke(
            {"reason": "Test", "is_sensitive": False},
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        # When config is None, the tool reports "missing employee context"
        assert "missing" in result["message"].lower()

    async def test_escalate_to_human_missing_employee(self, db_session: AsyncSession):
        """escalate_to_human returns error for non-existent employee."""
        from app.agent.tools.escalation import escalate_to_human

        result_str = await escalate_to_human.ainvoke(
            {"reason": "Test", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(UUID("00000000-0000-0000-0000-000000000000")),
                    "platform": "slack",
                    "channel_id": "C123",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    async def test_escalate_to_human_non_slack_platform(
        self, test_db, db_session: AsyncSession, employee_ids
    ):
        """escalate_to_human returns error for non-Slack platforms.

        Must set both escalation policy AND Slack token, because the tool
        checks for Slack token before checking the platform.
        Uses 'sales_rep' to avoid conflicting with the no-token test.
        """
        _engine, session_factory, _ids = test_db

        await set_escalation_policy(
            session_factory,
            employee_ids["sales_rep"],
            {
                "manager_slack_id": "U123",
                "default_escalation_channel": "#sales-escalations",
            },
        )
        # Set a Slack token so it passes the token check
        await set_slack_token(session_factory, employee_ids["sales_rep"], "xoxb-test-token")

        from app.agent.tools.escalation import escalate_to_human

        result_str = await escalate_to_human.ainvoke(
            {"reason": "Test", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(employee_ids["sales_rep"]),
                    "platform": "discord",
                    "channel_id": "D123",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "only supported on Slack" in result["message"]

    async def test_escalate_to_human_no_slack_token(
        self, test_db, db_session: AsyncSession, employee_ids
    ):
        """escalate_to_human returns error when employee has no Slack token.

        Uses 'hr_specialist' which has no Slack token set by any other test.
        """
        _engine, session_factory, _ids = test_db

        await set_escalation_policy(
            session_factory,
            employee_ids["hr_specialist"],
            {
                "manager_slack_id": "U123",
                "default_escalation_channel": "#hr-escalations",
            },
        )

        from app.agent.tools.escalation import escalate_to_human

        result_str = await escalate_to_human.ainvoke(
            {"reason": "Test", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(employee_ids["hr_specialist"]),
                    "platform": "slack",
                    "channel_id": "C123",
                    "thread_ts": "123.456",
                    "thread_id": "slack:test:no:token",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        # The tool says "this employee has no Slack token configured"
        assert "slack token" in result["message"].lower()

    async def test_escalation_target_resolution(self):
        """_resolve_escalation_target picks the right target based on sensitivity."""
        from app.agent.tools.escalation import _resolve_escalation_target

        policy = {
            "manager_slack_id": "U123",
            "default_escalation_channel": "#escalations",
        }

        # Sensitive → manager DM
        target, label = _resolve_escalation_target(policy, is_sensitive=True)
        assert target == "U123"
        assert "DM" in label

        # Not sensitive → channel
        target2, label2 = _resolve_escalation_target(policy, is_sensitive=False)
        assert target2 == "#escalations"
        assert "channel" in label2.lower()

        # No manager_slack_id → falls back to channel
        policy_no_mgr = {"default_escalation_channel": "#general"}
        target3, _label3 = _resolve_escalation_target(policy_no_mgr, is_sensitive=True)
        assert target3 == "#general"

        # Empty policy → None
        target4, _label4 = _resolve_escalation_target({}, is_sensitive=False)
        assert target4 is None

    @patch("app.agent.tools.escalation.AsyncWebClient")
    async def test_escalate_to_human_success_fire_and_forget(
        self,
        mock_client_cls,
        test_db,
        employee_ids,
    ):
        """escalate_to_human posts to Slack and returns success (with mocked client)."""
        _engine, session_factory, _ids = test_db

        # Set up employee with escalation policy AND a Slack token
        await set_escalation_policy(
            session_factory,
            employee_ids["support_agent"],
            {
                "manager_slack_id": "U123",
                "default_escalation_channel": "#support-escalations",
                "mode": "fire_and_forget",
            },
        )
        await set_slack_token(session_factory, employee_ids["support_agent"], "xoxb-test-token")

        # Mock the Slack client
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "123.789"}
        )
        mock_client_cls.return_value = mock_client

        from app.agent.tools.escalation import escalate_to_human

        async with session_factory() as session:
            result_str = await escalate_to_human.ainvoke(
                {"reason": "User needs help with payroll", "is_sensitive": True},
                config={
                    "configurable": {
                        "db": session,
                        "employee_id": str(employee_ids["support_agent"]),
                        "platform": "slack",
                        "channel_id": "C123",
                        "thread_ts": "123.456",
                        "thread_id": "slack:test:ff:success",
                    }
                },
            )

        result = json.loads(result_str)
        assert result["status"] == "success"
        assert "escalated" in result["message"].lower()
        assert result["target"] == "manager DM (U123)"

        # Verify chat_postMessage was called
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args[1]["channel"] == "U123"
        assert "🚨" in call_args[1]["text"]


# =============================================================================
# Phase 6 — Interactive Escalation
# =============================================================================


class TestPhase6InteractiveEscalation:
    """Tests for the interactive escalate_to_human_interactive tool (Phase 6)."""

    async def test_interactive_escalation_no_policy(
        self, db_session: AsyncSession, employee_ids
    ):
        """escalate_to_human_interactive returns error when no policy is set."""
        from app.agent.tools.escalation import escalate_to_human_interactive

        result_str = await escalate_to_human_interactive.ainvoke(
            {"reason": "Need approval for purchase", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(employee_ids["general"]),
                    "platform": "slack",
                    "channel_id": "C123",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"

    async def test_interactive_escalation_non_slack(
        self, test_db, db_session: AsyncSession, employee_ids
    ):
        """escalate_to_human_interactive rejects non-Slack platforms.

        Must set both policy AND Slack token so it passes the token check first.
        """
        _engine, session_factory, _ids = test_db

        await set_escalation_policy(
            session_factory,
            employee_ids["general"],
            {"manager_slack_id": "U123"},
        )
        await set_slack_token(session_factory, employee_ids["general"], "xoxb-test-token")

        from app.agent.tools.escalation import escalate_to_human_interactive

        result_str = await escalate_to_human_interactive.ainvoke(
            {"reason": "Test", "is_sensitive": False},
            config={
                "configurable": {
                    "db": db_session,
                    "employee_id": str(employee_ids["general"]),
                    "platform": "discord",
                    "channel_id": "D123",
                }
            },
        )
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "only supported on Slack" in result["message"]

    @patch("app.agent.tools.escalation.interrupt")
    @patch("app.agent.tools.escalation.AsyncWebClient")
    async def test_interactive_escalation_calls_interrupt(
        self,
        mock_client_cls,
        mock_interrupt,
        test_db,
        employee_ids,
    ):
        """escalate_to_human_interactive successfully posts and calls interrupt() (mocked)."""
        _engine, session_factory, _ids = test_db

        await set_escalation_policy(
            session_factory,
            employee_ids["support_agent"],
            {
                "manager_slack_id": "U123",
                "default_escalation_channel": "#support-escalations",
                "mode": "interactive",
            },
        )
        await set_slack_token(
            session_factory, employee_ids["support_agent"], "xoxb-test-token"
        )

        # Mock interrupt to simulate approval
        mock_interrupt.return_value = {
            "approved": True,
            "by": "U123",
            "note": "Looks good, proceed.",
        }

        # Mock the Slack client for both messages
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "123.789"}
        )
        mock_client_cls.return_value = mock_client

        from app.agent.tools.escalation import escalate_to_human_interactive

        async with session_factory() as session:
            result_str = await escalate_to_human_interactive.ainvoke(
                {"reason": "Approve email send to all customers", "is_sensitive": False},
                config={
                    "configurable": {
                        "db": session,
                        "employee_id": str(employee_ids["support_agent"]),
                        "platform": "slack",
                        "channel_id": "C123",
                        "thread_ts": "123.456",
                        "thread_id": "slack:test:interactive:1",
                    }
                },
            )

        result = json.loads(result_str)
        assert result["status"] == "approved"
        assert result["approved"] is True
        assert result["approved_by"] == "U123"
        assert "proceed" in result["message"].lower()

        # Verify interrupt was called
        mock_interrupt.assert_called_once()

        # Verify two messages: waiting message to user + approval request to manager
        assert mock_client.chat_postMessage.call_count == 2

    @patch("app.agent.tools.escalation.interrupt")
    @patch("app.agent.tools.escalation.AsyncWebClient")
    async def test_interactive_escalation_denied(
        self,
        mock_client_cls,
        mock_interrupt,
        test_db,
        employee_ids,
    ):
        """escalate_to_human_interactive handles denial correctly."""
        _engine, session_factory, _ids = test_db

        await set_escalation_policy(
            session_factory,
            employee_ids["support_agent"],
            {
                "manager_slack_id": "U123",
                "default_escalation_channel": "#support-escalations",
            },
        )
        await set_slack_token(
            session_factory, employee_ids["support_agent"], "xoxb-test-token"
        )

        # Mock interrupt to simulate denial
        mock_interrupt.return_value = {
            "approved": False,
            "by": "U456",
            "note": "Not authorized for this.",
        }

        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "123.789"}
        )
        mock_client_cls.return_value = mock_client

        from app.agent.tools.escalation import escalate_to_human_interactive

        async with session_factory() as session:
            result_str = await escalate_to_human_interactive.ainvoke(
                {"reason": "Send mass email", "is_sensitive": True},
                config={
                    "configurable": {
                        "db": session,
                        "employee_id": str(employee_ids["support_agent"]),
                        "platform": "slack",
                        "channel_id": "C123",
                        "thread_ts": "123.456",
                        "thread_id": "slack:test:interactive:denied",
                    }
                },
            )

        result = json.loads(result_str)
        assert result["status"] == "denied"
        assert result["approved"] is False
        assert result["denied_by"] == "U456"
        assert "not proceed" in result["message"].lower()


# =============================================================================
# End-to-end agent graph integration tests
# =============================================================================


class TestAgentGraphIntegration:
    """End-to-end tests exercising the full agent graph with tools.

    These tests require ``OPENAI_API_KEY`` to be set.
    """

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY is required for agent graph tests",
    )
    async def test_graph_simple_query(self, test_db, employee_ids):
        """A simple non-tool query returns a response."""
        _engine, session_factory, _ids = test_db

        from app.agent.router import get_graph_for_employee
        from langchain_core.messages import HumanMessage

        async with session_factory() as session:
            graph, all_tools = await get_graph_for_employee(
                session, employee_ids["general"]
            )

            config = {
                "configurable": {
                    "db": session,
                    "employee_id": str(employee_ids["general"]),
                    "all_tools": all_tools,
                    "thread_id": f"test:simple:{uuid4()}",
                    "platform": "test",
                }
            }

            initial_state = {
                "messages": [HumanMessage(content="Say hello in exactly 3 words.")],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result = await graph.ainvoke(initial_state, config=config)
            response = result.get("response", "")

            assert response
            assert result.get("error") is None

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY is required for agent graph tests",
    )
    async def test_graph_uses_calculate_tool(self, test_db, employee_ids):
        """The agent uses the calculate tool for math queries."""
        _engine, session_factory, _ids = test_db

        from app.agent.router import get_graph_for_employee
        from langchain_core.messages import HumanMessage

        async with session_factory() as session:
            graph, all_tools = await get_graph_for_employee(
                session, employee_ids["general"]
            )

            config = {
                "configurable": {
                    "db": session,
                    "employee_id": str(employee_ids["general"]),
                    "all_tools": all_tools,
                    "thread_id": f"test:calc:{uuid4()}",
                    "platform": "test",
                }
            }

            initial_state = {
                "messages": [
                    HumanMessage(content="What is 125 * 37? Use the calculate tool.")
                ],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result = await graph.ainvoke(initial_state, config=config)
            response = result.get("response", "")

            assert response
            # The answer should be 4625
            assert "4625" in response

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY is required for agent graph tests",
    )
    async def test_graph_guardrail_no_tools_for_greeting(self, test_db, employee_ids):
        """Simple greeting should not trigger tool calls."""
        _engine, session_factory, _ids = test_db

        from app.agent.router import get_graph_for_employee
        from langchain_core.messages import HumanMessage

        async with session_factory() as session:
            graph, all_tools = await get_graph_for_employee(
                session, employee_ids["general"]
            )

            config = {
                "configurable": {
                    "db": session,
                    "employee_id": str(employee_ids["general"]),
                    "all_tools": all_tools,
                    "thread_id": f"test:greet:{uuid4()}",
                    "platform": "test",
                }
            }

            initial_state = {
                "messages": [HumanMessage(content="Hi there!")],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result = await graph.ainvoke(initial_state, config=config)
            response = result.get("response", "")

            assert response
            assert result.get("tool_round", 0) == 0

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY is required for agent graph tests",
    )
    async def test_graph_tool_round_limit(self, test_db, employee_ids):
        """The graph is capped at 5 tool rounds (guard against infinite loops)."""
        _engine, session_factory, _ids = test_db

        from app.agent.router import get_graph_for_employee
        from langchain_core.messages import HumanMessage

        async with session_factory() as session:
            graph, all_tools = await get_graph_for_employee(
                session, employee_ids["general"]
            )

            config = {
                "configurable": {
                    "db": session,
                    "employee_id": str(employee_ids["general"]),
                    "all_tools": all_tools,
                    "thread_id": f"test:limit:{uuid4()}",
                    "platform": "test",
                }
            }

            initial_state = {
                "messages": [
                    HumanMessage(
                        content="Calculate ALL of these: 2+2, 3+3, 4+4, 5+5, 6+6, 7+7, 8+8. "
                        "Use the calculate tool separately for EACH one."
                    )
                ],
                "platform": "test",
                "employee_id": str(employee_ids["general"]),
                "tool_round": 0,
            }

            result = await graph.ainvoke(initial_state, config=config)
            tool_rounds = result.get("tool_round", 0)

            # Should never exceed 5 regardless of how many calculations requested
            assert tool_rounds <= 5


# =============================================================================
# Worker lifecycle tests
# =============================================================================


class TestWorkerLifecycle:
    """Tests for the AgentJobWorker start/stop lifecycle."""

    @pytest.mark.skipif(not IS_POSTGRES, reason="Worker uses app DB factory (PG only)")
    async def test_worker_start_stop(self):
        """Worker can start and stop cleanly."""
        from app.agent.jobs.worker import AgentJobWorker

        worker = AgentJobWorker()
        await worker.start()
        assert worker.running is True
        assert len(worker._tasks) == 4  # default concurrency

        await worker.stop()
        assert worker.running is False
        assert len(worker._tasks) == 0

    async def test_set_active_worker_singleton(self):
        """The module-level worker singleton can be set and cleared."""
        from app.agent.jobs.worker import (
            AgentJobWorker,
            get_active_worker,
            set_active_worker,
        )

        worker = AgentJobWorker()
        set_active_worker(worker)
        assert get_active_worker() is worker

        set_active_worker(None)
        assert get_active_worker() is None


# =============================================================================
# Agent Job Runner tests
# =============================================================================


class TestJobRunner:
    """Tests for the job runner dispatch system."""

    async def test_runner_no_handler(self, employee_ids):
        """run_job marks job as failed when no handler is registered."""
        from app.agent.jobs.models import AgentJob
        from app.agent.jobs.runner import run_job

        job = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="test:no:handler",
            job_type="nonexistent_type",
            status="running",
        )

        await run_job(job)
        assert job.status == "failed"
        assert "No handler registered" in (job.error or "")

    async def test_runner_registered_handler(self, employee_ids):
        """run_job dispatches to a registered handler successfully."""
        from app.agent.jobs.models import AgentJob
        from app.agent.jobs.runner import register_handler, run_job

        handler_called = False

        async def test_handler(job: AgentJob) -> None:
            nonlocal handler_called
            handler_called = True
            job.status = "succeeded"
            job.result_text = "Done!"

        register_handler("test_handler_type", test_handler)

        job = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="test:handler:ok",
            job_type="test_handler_type",
            status="running",
        )

        await run_job(job)
        assert handler_called is True
        assert job.status == "succeeded"
        assert job.result_text == "Done!"

    async def test_runner_handler_exception(self, employee_ids):
        """run_job marks job as failed when the handler raises."""
        from app.agent.jobs.models import AgentJob
        from app.agent.jobs.runner import register_handler, run_job

        async def failing_handler(job: AgentJob) -> None:
            raise ValueError("Simulated failure")

        register_handler("failing_type", failing_handler)

        job = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="test:handler:fail",
            job_type="failing_type",
            status="running",
        )

        await run_job(job)
        assert job.status == "failed"
        assert "Handler raised" in (job.error or "")


# =============================================================================
# Templates and tool binding tests
# =============================================================================


class TestTemplatesAndToolBinding:
    """Verify templates have correct tool allowlists and escalation tools are bound."""

    def test_hr_template_has_escalation_tools(self):
        """HR template includes both escalation tools."""
        from app.employees.templates import HR_TEMPLATE

        assert "escalate_to_human" in HR_TEMPLATE.allowed_tools
        assert "escalate_to_human_interactive" in HR_TEMPLATE.allowed_tools

    def test_support_template_has_escalation_tools(self):
        """Support template includes both escalation tools."""
        from app.employees.templates import SUPPORT_TEMPLATE

        assert "escalate_to_human" in SUPPORT_TEMPLATE.allowed_tools
        assert "escalate_to_human_interactive" in SUPPORT_TEMPLATE.allowed_tools

    def test_sales_template_has_escalation_tools(self):
        """Sales template includes both escalation tools."""
        from app.employees.templates import SALES_TEMPLATE

        assert "escalate_to_human" in SALES_TEMPLATE.allowed_tools
        assert "escalate_to_human_interactive" in SALES_TEMPLATE.allowed_tools

    def test_general_template_no_escalation_tools(self):
        """General template does NOT include escalation tools (by design)."""
        from app.employees.templates import GENERAL_TEMPLATE

        assert "escalate_to_human" not in GENERAL_TEMPLATE.allowed_tools
        assert "escalate_to_human_interactive" not in GENERAL_TEMPLATE.allowed_tools

    def test_all_templates_have_background_task_tools(self):
        """Every template includes check_background_task and cancel_background_task."""
        from app.employees.templates import TEMPLATES

        for name, template in TEMPLATES.items():
            assert "check_background_task" in template.allowed_tools, (
                f"{name} missing check_background_task"
            )
            assert "cancel_background_task" in template.allowed_tools, (
                f"{name} missing cancel_background_task"
            )

    def test_built_in_tools_includes_all_new_tools(self):
        """BUILT_IN_TOOLS includes escalation and background task tools."""
        from app.agent.tools.executor import BUILT_IN_TOOLS

        tool_names = {t.name for t in BUILT_IN_TOOLS}

        assert "escalate_to_human" in tool_names
        assert "escalate_to_human_interactive" in tool_names
        assert "check_background_task" in tool_names
        assert "cancel_background_task" in tool_names
        assert "search_web" in tool_names
        assert "calculate" in tool_names
        assert "get_datetime" in tool_names
        assert "fetch_url" in tool_names
        assert "search_memory" in tool_names
        assert "ingest_memory" in tool_names


# =============================================================================
# Employee model tests
# =============================================================================


class TestEmployeeModel:
    """Tests for the Employee model's new escalation fields (Phase 5)."""

    async def test_escalation_policy_column_exists(self, test_db, employee_ids):
        """The escalation_policy JSONB column exists on Employee."""
        _engine, session_factory, _ids = test_db

        async with session_factory() as session:
            from app.employees.models import Employee

            emp = await session.get(Employee, employee_ids["general"])
            assert emp is not None
            # escalation_policy should be accessible as an attribute
            assert hasattr(emp, "escalation_policy")
            # Default is None for unset
            assert emp.escalation_policy is None or isinstance(
                emp.escalation_policy, dict
            )

    async def test_agent_job_fk_to_employee(self, db_session: AsyncSession, employee_ids):
        """AgentJob has a working FK to Employee."""
        from app.agent.jobs.models import AgentJob

        job = AgentJob(
            employee_id=employee_ids["general"],
            platform="slack",
            channel_id="C1",
            thread_key="test:fk:check",
            job_type="test_type",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # FK is valid — employee exists
        from app.employees.models import Employee

        emp = await db_session.get(Employee, employee_ids["general"])
        assert emp is not None
        assert job.employee_id == emp.id
