"""Postgres-backed LangGraph checkpointer (Phase 4).

Provides a module-level :class:`AsyncPostgresSaver` singleton that persists
agent conversation state (thread memory) across invocations.  This is what
enables pause/resume, interactive approval, and true conversational memory
without re-fetching Slack history on every turn.

Initialized during FastAPI lifespan in :mod:`app.main` and closed on shutdown.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_saver: AsyncPostgresSaver | None = None
"""The shared checkpointer instance, or ``None`` before initialization."""

_context: object | None = None
"""The async context manager returned by ``from_conn_string``.

Stored so we can call ``__aexit__`` during shutdown to release the
underlying psycopg connection pool cleanly.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_checkpointer() -> AsyncPostgresSaver | None:
    """Return the module-level :class:`AsyncPostgresSaver` singleton.

    Returns ``None`` before :func:`init_checkpointer` has been called
    (e.g. during module import or before the FastAPI lifespan runs).
    Callers that require a checkpointer should guard against ``None``.
    """
    return _saver


from contextlib import asynccontextmanager
import psycopg
from psycopg.rows import dict_row

@asynccontextmanager
async def _custom_conn_context(conn_string: str):
    async with await psycopg.AsyncConnection.connect(
        conn_string,
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
    ) as conn:
        yield AsyncPostgresSaver(conn=conn)


async def init_checkpointer() -> None:
    """Create the AsyncPostgresSaver singleton and run migrations.

    Uses ``checkpoint_database_url`` if configured; otherwise derives a
    psycopg-compatible DSN from ``database_url`` by stripping the
    ``+asyncpg`` driver specifier.

    Safe to call when already initialized (no-op).
    """
    global _saver, _context

    if _saver is not None:
        logger.debug("Checkpointer already initialized — skipping.")
        return

    dsn = _derive_psycopg_dsn()
    logger.info("Initializing Postgres checkpointer (db=%s...)", _redact_dsn(dsn))

    # We manually establish connection with prepare_threshold=None to prevent
    # psycopg from using prepared statements, which ensures compatibility
    # with PgBouncer in transaction mode (Supabase pooled port 6543).
    _context = _custom_conn_context(dsn)
    _saver = await _context.__aenter__()
    await _saver.setup()

    logger.info("Postgres checkpointer ready.")


async def close_checkpointer() -> None:
    """Shut down the checkpointer and release its connection pool.

    Safe to call when not initialized (no-op).
    """
    global _saver, _context

    if _context is not None:
        await _context.__aexit__(None, None, None)
        _saver = None
        _context = None
        logger.info("Postgres checkpointer closed.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_psycopg_dsn() -> str:
    """Return a psycopg-compatible DSN for the checkpointer.

    Uses ``checkpoint_database_url`` if set; otherwise derives one
    from ``database_url`` by stripping the ``+asyncpg`` driver specifier.
    """
    if settings.checkpoint_database_url:
        return settings.checkpoint_database_url
    # postgresql+asyncpg://user:pass@host:port/db → postgresql://user:pass@host:port/db
    return settings.database_url.replace("+asyncpg", "")


def _redact_dsn(dsn: str) -> str:
    """Return a safe-for-logging version of *dsn* with password masked."""
    if "@" in dsn:
        prefix, rest = dsn.split("@", 1)
        if ":" in prefix:
            proto_user = prefix.rsplit(":", 1)[0]
            return f"{proto_user}:****@{rest}"
    return dsn[:50]
