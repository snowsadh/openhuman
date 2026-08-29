"""Memory-conscious API entrypoint for constrained ZopDay containers.

The full application imports the agent, Cognee, Slack, Discord, MCP, and
scheduler stacks during process startup.  Those integrations remain available
through ``app.main`` for normal deployments, while this entrypoint keeps the
core web application usable within ZopDay's smaller service memory limit.
"""

import logging
import subprocess
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import inspect, text

# Register every SQLAlchemy model before migrations and request handling so
# relationship strings can be resolved without importing heavyweight routers.
import app.agent.jobs.models  # noqa: F401
import app.agent.tools.mcp.models  # noqa: F401
import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401
import app.schedules.models  # noqa: F401
from app.activity.router import router as activity_router
from app.agent.tools.mcp.catalog import register_catalog_connectors
from app.auth.router import router as auth_router
from app.channel_assignments.router import router as ca_router
from app.core.config import settings
from app.core.database import Base, engine
from app.documents.router import router as doc_router
from app.employees.router import router as emp_router
from app.health.router import router as health_router
from app.mcp.router import oauth_router as mcp_oauth_router
from app.mcp.router import router as mcp_router
from app.organizations.router import router as org_router
from app.zop_agent_router import router as agent_router
from app.zop_armoriq import router as armoriq_router

logger = logging.getLogger(__name__)
database_bootstrap_error: dict[str, str] | None = None


def custom_generate_unique_id(route: APIRoute) -> str:
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


def _build_allowed_origins() -> list[str]:
    origins = list(settings.cors_origins)
    frontend_url = settings.frontend_url.strip()
    if frontend_url and frontend_url not in origins:
        parsed = urlparse(frontend_url)
        if parsed.scheme and parsed.netloc:
            origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return origins


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Apply migrations without making an already-provisioned API crash-loop.

    Zop restarts containers automatically. A transient database or migration
    failure must not prevent the health endpoint from becoming ready; request
    paths that need the database can report their own actionable error while
    the service stays observable.
    """
    registered_connectors = register_catalog_connectors()
    logger.info("Registered %d catalog MCP connectors for Zop", registered_connectors)

    if settings.database_url.startswith("mysql+"):
        global database_bootstrap_error
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        except Exception as exc:
            database_bootstrap_error = {
                "error_type": type(exc).__name__,
                "message": str(getattr(exc, "orig", exc))[:500],
            }
            logger.exception("MySQL schema bootstrap failed; continuing API startup")
    else:
        logger.info("Running database migrations")
        try:
            subprocess.run(
                ["alembic", "upgrade", "heads"],
                check=True,
                timeout=120,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.exception("Database migration failed; continuing API startup")
            try:
                async with engine.begin() as connection:
                    table_names = await connection.run_sync(
                        lambda sync_connection: inspect(sync_connection).get_table_names()
                    )
                    if "users" not in table_names:
                        logger.warning(
                            "Database is empty; creating the current schema from ORM metadata"
                        )
                        await connection.run_sync(Base.metadata.create_all)
            except Exception:
                logger.exception("Empty-database schema bootstrap failed")
        else:
            logger.info("Database migrations completed")
    yield


app = FastAPI(
    title="OpenHuman API",
    version="0.1.0",
    description="OpenHuman — core API (ZopDay deployment)",
    lifespan=lifespan,
    separate_input_output_schemas=False,
    generate_unique_id_function=custom_generate_unique_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_allowed_origins(),
    allow_origin_regex=(
        r"https://.*\.vercel\.app"
        r"|https://.*\.up\.railway\.app"
        r"|http://localhost(:\d+)?"
        r"|http://127\.0\.0\.1(:\d+)?"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health/database", tags=["health"])
async def database_health() -> dict:
    """Report schema readiness without exposing credentials or application data."""
    expected_user_columns = {
        "id",
        "clerk_id",
        "email",
        "name",
        "password_hash",
        "is_active",
        "onboarding_completed",
        "created_at",
        "updated_at",
    }
    try:
        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
            actual_user_columns: set[str] = set()
            if "users" in table_names:
                actual_user_columns = set(
                    await connection.run_sync(
                        lambda sync_connection: [
                            column["name"]
                            for column in inspect(sync_connection).get_columns("users")
                        ]
                    )
                )
            versions: list[str] = []
            if "alembic_version" in table_names:
                version_rows = await connection.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                )
                versions = [row[0] for row in version_rows]
        missing = sorted(expected_user_columns - actual_user_columns)
        return {
            "status": "ok" if not missing else "schema_incomplete",
            "database_connected": True,
            "users_table_present": bool(actual_user_columns),
            "missing_user_columns": missing,
            "alembic_versions": versions,
            "bootstrap_error": database_bootstrap_error,
        }
    except Exception as exc:
        logger.exception("Database health check failed")
        return {
            "status": "unavailable",
            "database_connected": False,
            "error_type": type(exc).__name__,
        }


app.include_router(health_router)
app.include_router(activity_router)
app.include_router(agent_router)
app.include_router(armoriq_router)
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(emp_router)
app.include_router(ca_router)
app.include_router(doc_router)
app.include_router(mcp_router)
app.include_router(mcp_oauth_router)
