"""Memory-conscious API entrypoint for constrained ZopDay containers.

The full application imports the agent, Cognee, Slack, Discord, MCP, and
scheduler stacks during process startup.  Those integrations remain available
through ``app.main`` for normal deployments, while this entrypoint keeps the
core web application usable within ZopDay's smaller service memory limit.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
import subprocess
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

# Register every SQLAlchemy model before migrations and request handling so
# relationship strings can be resolved without importing heavyweight routers.
import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401
import app.agent.jobs.models  # noqa: F401
import app.agent.tools.mcp.models  # noqa: F401
import app.schedules.models  # noqa: F401

from app.activity.router import router as activity_router
from app.auth.router import router as auth_router
from app.channel_assignments.router import router as ca_router
from app.core.config import settings
from app.documents.router import router as doc_router
from app.employees.router import router as emp_router
from app.health.router import router as health_router
from app.organizations.router import router as org_router

logger = logging.getLogger(__name__)


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
    logger.info("Running database migrations")
    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.exception("Database migration failed; continuing API startup")
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

app.include_router(health_router)
app.include_router(activity_router)
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(emp_router)
app.include_router(ca_router)
app.include_router(doc_router)
