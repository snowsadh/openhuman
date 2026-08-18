import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the app package importable when running alembic from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import Base

# Import all model modules so their table definitions register with Base.metadata
import app.auth.models  # noqa: F401, E402
import app.channel_assignments.models  # noqa: F401, E402
import app.documents.models  # noqa: F401, E402
import app.employees.models  # noqa: F401, E402
import app.organizations.models  # noqa: F401, E402
import app.activity.models  # noqa: F401, E402
import app.agent.tools.mcp.models  # noqa: F401, E402
import app.agent.jobs.models  # noqa: F401, E402

# this is the Alembic Config object
config = context.config

# Override the placeholder URL in alembic.ini with our settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with an async engine."""
    connect_args = {}
    if settings.database_url.startswith("postgresql+asyncpg"):
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())
    print(">>> Alembic migrations completed successfully!", flush=True)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

