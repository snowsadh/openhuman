"""
Shared test fixtures for CLI and Streamlit agent test tools.

Creates an isolated SQLite database with all tables and seeds a minimal
organisation + employee hierarchy so the agent graph has real data to work with.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, event, pool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure the api package is importable when running from the test/ directory
_this_dir = Path(__file__).resolve().parent
_api_dir = _this_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

# Import models so their __table__ objects are registered
import app.agent.tools.mcp.models  # noqa: F401  — McpConnection
import app.auth.models  # noqa: F401  — User
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401  — Employee
import app.organizations.models  # noqa: F401  — Organization
# app.gateway.models removed — SlackAppSlot table was dropped in the fixed-bot migration
import os

from app.auth.models import User
from app.core.config import settings
from app.core.database import Base
from app.core.security import encrypt_token, decrypt_token
from app.employees.models import Employee
from app.employees.templates import TEMPLATES, EmployeeTemplate
from app.organizations.models import Organization

# ---------------------------------------------------------------------------
# Ensure an encryption key is available for test token storage.
# In production this MUST be set explicitly.  For test tools we use a
# deterministic default so tokens survive across process invocations
# (encrypted in one CLI run, decrypted in the next).
# ---------------------------------------------------------------------------
_TEST_FALLBACK_KEY = (
    "6f70656e68756d616e2d746573742d6b65792d666f722d746f6b656e73212121"
)  # "openhuman-test-key-for-tokens!!!" → 32 bytes / 64 hex chars
if not settings.encryption_key:
    settings.encryption_key = _TEST_FALLBACK_KEY

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


# ---------------------------------------------------------------------------
# Pre-built seed employee configs — one per template
# ---------------------------------------------------------------------------

SEED_EMPLOYEES: list[dict] = [
    {
        "name": "Alex (HR)",
        "specialization": "hr_specialist",
        "role": "Human Resources Specialist",
        "personality": {"tone": "empathetic", "traits": ["professional", "supportive"]},
        "duties": ["Answer policy questions", "Screen resumes"],
    },
    {
        "name": "Blake (Sales)",
        "specialization": "sales_rep",
        "role": "Sales Development Representative",
        "personality": {"tone": "energetic", "traits": ["concise", "results-driven"]},
        "duties": ["Qualify leads", "Draft pipeline summaries"],
    },
    {
        "name": "Casey (Support)",
        "specialization": "support_agent",
        "role": "Customer Support Specialist",
        "personality": {"tone": "warm", "traits": ["patient", "empathetic"]},
        "duties": ["Answer support questions", "Escalate complex issues"],
    },
    {
        "name": "Drew (General)",
        "specialization": "general",
        "role": "AI Assistant",
        "personality": {"tone": "helpful", "traits": ["accurate", "concise"]},
        "duties": ["Answer general questions", "Help with research"],
    },
]

# Cached seed IDs so callers can reference them after setup
SEED_USER_ID: UUID | None = None
SEED_ORG_ID: UUID | None = None
SEED_EMPLOYEE_IDS: dict[str, UUID] = {}  # specialization → UUID


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------


def _build_engine(db_path: str | Path, poolclass: pool.Pool | None = None) -> AsyncEngine:
    """Create an async engine.

    When *db_path* starts with ``postgresql://`` or ``postgresql+asyncpg://``
    it is treated as a full database URL (useful for sharing the API's
    database during OAuth tests).  Otherwise it is treated as a SQLite path.
    """
    path_str = str(db_path)
    kwargs = {}
    if poolclass is not None:
        kwargs["poolclass"] = poolclass

    if path_str.startswith("postgresql"):
        return create_async_engine(path_str, **kwargs)

    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url, **kwargs)

    @event.listens_for(engine.sync_engine, "connect")
    def _register_uuid(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    return engine


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_tables(engine: AsyncEngine) -> None:
    """Create all ORM tables.  Automatically handles SQLite vs PostgreSQL.

    For SQLite, swaps ``JSONB`` → ``JSON`` before DDL because SQLite has
    no JSONB type.  For PostgreSQL, creates tables as-is.
    """
    is_sqlite = "sqlite" in str(engine.url)

    if is_sqlite:
        # Patch JSONB → JSON on every column in every table.
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if isinstance(column.type, JSONB):
                    column.type = JSON()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_data(session: AsyncSession) -> dict[str, UUID]:
    """Insert a test user, org, and four employees (one per template).

    Returns a dict mapping specialisation slug → employee UUID so callers
    can pick which employee to test.
    """
    global SEED_USER_ID, SEED_ORG_ID, SEED_EMPLOYEE_IDS  # noqa: PLW0603

    user_id = uuid4()
    org_id = uuid4()

    user = User(
        id=user_id,
        email="test@openhuman.local",
        clerk_id="user_test_123",
        name="Test User",
        is_active=True,
    )
    org = Organization(id=org_id, owner_id=user_id, name="Test Corp")

    session.add(user)
    session.add(org)

    employee_ids: dict[str, UUID] = {}
    for cfg in SEED_EMPLOYEES:
        emp_id = uuid4()
        template = TEMPLATES[cfg["specialization"]]
        emp = Employee(
            id=emp_id,
            org_id=org_id,
            name=cfg["name"],
            role=cfg["role"],
            specialization=cfg["specialization"],
            personality=cfg["personality"],
            duties=cfg["duties"],
            status="active",
        )
        session.add(emp)
        employee_ids[cfg["specialization"]] = emp_id

    await session.commit()

    SEED_USER_ID = user_id
    SEED_ORG_ID = org_id
    SEED_EMPLOYEE_IDS = employee_ids

    return employee_ids


async def setup_test_db(
    db_path: str | Path = ":memory:",
    poolclass: pool.Pool | None = None,
) -> tuple[AsyncEngine, async_sessionmaker, dict[str, UUID]]:
    """One-shot: create engine, tables, seed data.

    If the database already contains the seed employees, the existing data
    is reused and the cached ``SEED_EMPLOYEE_IDS`` are returned.  This makes
    repeated invocations against the same file-based database idempotent.

    When *db_path* is a PostgreSQL URL (e.g. ``USE_API_DB=true``), tables
    are assumed to already exist (via Alembic migrations) and only seed data
    is inserted if missing.

    Returns (engine, session_factory, employee_ids).
    """
    global SEED_EMPLOYEE_IDS

    path_str = str(db_path)
    is_pg = path_str.startswith("postgresql")

    engine = _build_engine(path_str, poolclass=poolclass)

    if is_pg:
        # API database — tables already exist via Alembic migrations.
        # Just verify we can connect; don't try to create tables.
        async with engine.connect() as conn:
            await conn.close()
    else:
        await create_tables(engine)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # If we already have cached IDs from a prior seeding, reuse them
    if SEED_EMPLOYEE_IDS:
        return engine, session_factory, SEED_EMPLOYEE_IDS

    # Check whether seed data already exists in this DB
    async with session_factory() as session:
        from sqlalchemy import select, func

        count = await session.scalar(select(func.count()).select_from(Employee))
        if count and count >= len(SEED_EMPLOYEES):
            # Reconstruct the ID map from existing rows
            result = await session.execute(
                select(Employee).where(Employee.specialization.in_(
                    [cfg["specialization"] for cfg in SEED_EMPLOYEES]
                ))
            )
            employee_ids: dict[str, UUID] = {}
            for emp in result.scalars().all():
                employee_ids[emp.specialization] = emp.id
            SEED_EMPLOYEE_IDS = employee_ids
            return engine, session_factory, employee_ids

        # Fresh seed
        employee_ids = await seed_data(session)

    return engine, session_factory, employee_ids


def print_banner() -> None:
    """Print a summary of available seed employees to the terminal."""
    print("\n📋 Available test employees:\n")
    for cfg in SEED_EMPLOYEES:
        template = TEMPLATES[cfg["specialization"]]
        eid = SEED_EMPLOYEE_IDS.get(cfg["specialization"], UUID(int=0))
        print(f"  {cfg['name']:<20s}  id={eid}")
        print(f"    Template : {template.name}")
        print(f"    Tools   : {', '.join(template.allowed_tools)}")
        print()


# ---------------------------------------------------------------------------
# Slack token helpers — for testing the token storage & OAuth flow
# ---------------------------------------------------------------------------


async def set_slack_token(
    session_factory: async_sessionmaker,
    employee_id: UUID,
    token: str,
) -> bool:
    """Store an encrypted Slack bot token on a seed employee.

    Returns ``True`` if the employee was found and updated.
    """
    async with session_factory() as session:
        emp = await session.get(Employee, employee_id)
        if emp is None:
            return False
        emp.slack_token_enc = encrypt_token(token)
        await session.commit()
    return True


async def clear_slack_token(
    session_factory: async_sessionmaker,
    employee_id: UUID,
) -> bool:
    """Remove the Slack bot token from a seed employee.

    Returns ``True`` if the employee was found.
    """
    async with session_factory() as session:
        emp = await session.get(Employee, employee_id)
        if emp is None:
            return False
        emp.slack_token_enc = None
        await session.commit()
    return True


async def get_slack_token_status(
    session_factory: async_sessionmaker,
    employee_id: UUID,
) -> bool:
    """Return ``True`` if the employee has a Slack token stored."""
    async with session_factory() as session:
        emp = await session.get(Employee, employee_id)
        if emp is None:
            return False
        return emp.slack_token_enc is not None


# ---------------------------------------------------------------------------
# Slack app slot helpers — REMOVED (slot-based provisioning is deprecated)
# ---------------------------------------------------------------------------
# The slack_app_slots table and SlackAppSlot model were dropped in the
# fixed-bot migration (a1147141b092).  Slot helpers (seed_slack_slots,
# provision_test_slots, get_slot_summary, get_employee_slot_status,
# assign_slot_to_employee, release_employee_slot) are no longer available.
# Use the fixed-bot registry (app.gateway.fixed_bots) for test setup instead.
#
# To test Slack OAuth with a fixed bot, set the SLACK_BOT_<TYPE>_* env vars
# and create an employee with the matching employee_type.


# ---------------------------------------------------------------------------
# Escalation policy helpers (Phase 5-6)
# ---------------------------------------------------------------------------


async def set_escalation_policy(
    session_factory: async_sessionmaker,
    employee_id: UUID,
    policy: dict,
) -> bool:
    """Set the escalation_policy JSONB field on a seed employee.

    *policy* should be a dict with keys like ``manager_slack_id``,
    ``default_escalation_channel``, ``mode`` (``"fire_and_forget"`` or
    ``"interactive"``).

    Returns ``True`` if the employee was found and updated.
    """
    async with session_factory() as session:
        emp = await session.get(Employee, employee_id)
        if emp is None:
            return False
        emp.escalation_policy = policy
        await session.commit()
    return True


async def get_escalation_policy(
    session_factory: async_sessionmaker,
    employee_id: UUID,
) -> dict | None:
    """Return the escalation policy for an employee, or ``None``."""
    async with session_factory() as session:
        emp = await session.get(Employee, employee_id)
        if emp is None:
            return None
        return emp.escalation_policy
