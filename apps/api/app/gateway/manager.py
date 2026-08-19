"""
Bot Gateway Manager — lifecycle for Discord and Slack bot connections.

Runs a background refresh loop that polls the database for active employees
and reconciles the set of running bot clients.

**Slack (shared mode):** One :class:`WorkspaceSlackBot` per unique bot token.
Multiple employees in the same Slack workspace share one token and one Socket
Mode connection.  The bot routes messages via ``channel_assignments``.

**Slack (per_employee mode):** One :class:`EmployeeSlackBot` per employee
(each has its own Slack app identity).  Mirrors the Discord architecture.
"""

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from app.activity.service import record_activity
from app.core.config import settings
from app.core.database import async_session_factory
from app.employees.models import Employee
from app.employees.service import (
    decrypt_discord_token,
    decrypt_slack_token,
    get_active_employees_with_tokens,
)
from app.gateway.discord_bot import EmployeeDiscordBot
from app.gateway.fixed_bots import get_fixed_bot
from app.gateway.slack_bot import EmployeeSlackBot, WorkspaceSlackBot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry / backoff constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_DELAY = 10  # seconds — exponential backoff: 10, 20, 40


class BotGatewayManager:
    """Manages continuous background lifecycle of Discord/Slack bots for
    active AI employees.

    The refresh loop polls the database every 60 seconds and reconciles the
    set of running bot clients with the active employee rows.
    """

    def __init__(self) -> None:
        # Discord: one client per employee (each has their own token)
        self.discord_bots: dict[UUID, tuple[EmployeeDiscordBot, asyncio.Task[None]]] = {}

        # Slack: storage differs by identity mode
        #   shared:       dict[token_str, WorkspaceSlackBot]
        #   per_employee: dict[employee_id, EmployeeSlackBot]
        self.slack_bots: dict[str, WorkspaceSlackBot] | dict[UUID, EmployeeSlackBot] = {}

        # Import WorkspaceSlackBot is still needed for shared mode; keep the ref
        # alive so tests/imports don't break.
        self._WorkspaceSlackBot = WorkspaceSlackBot  # noqa: N806

        self.refresh_task: asyncio.Task[None] | None = None
        self.running: bool = False


    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background refresh loop to poll active employee bots."""
        self.running = True
        self.refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("Bot Gateway Manager started.")

    async def stop(self) -> None:
        """Stop all running bots and cancel the refresh loop."""
        self.running = False
        if self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass

        # Shut down Discord bots
        for emp_id in list(self.discord_bots.keys()):
            await self._stop_discord_bot(emp_id)

        # Shut down Slack bots
        if settings.slack_identity_mode == "per_employee":
            slack_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]
            for emp_id in list(slack_bots.keys()):
                await self._stop_employee_slack_bot(emp_id)
        else:
            shared_bots: dict[str, WorkspaceSlackBot] = self.slack_bots  # type: ignore[assignment]
            for token in list(shared_bots.keys()):
                await self._stop_workspace_slack_bot(token)

        logger.info("Bot Gateway Manager stopped.")

    # ------------------------------------------------------------------
    # Refresh loop
    # ------------------------------------------------------------------

    async def _refresh_loop(self) -> None:
        while self.running:
            try:
                await self.refresh_bots()
            except Exception:
                logger.exception("Unhandled error in gateway refresh loop")
            await asyncio.sleep(60)

    async def refresh_bots(self) -> None:
        """Poll database and synchronize running bots with active DB rows."""
        async with async_session_factory() as db:
            active_employees = await get_active_employees_with_tokens(db)

        # --- Discord (unchanged: one bot per employee) ------------------------
        active_emp_ids = {emp.id for emp in active_employees}

        for emp_id in list(self.discord_bots.keys()):
            if emp_id not in active_emp_ids:
                await self._stop_discord_bot(emp_id)

        for emp in active_employees:
            await self._reconcile_discord_bot(emp)

        # --- Slack ------------------------------------------------------------
        if settings.slack_identity_mode == "fixed":
            await self._reconcile_slack_bots_fixed(active_employees)
        elif settings.slack_identity_mode == "per_employee":
            await self._reconcile_slack_bots_per_employee(active_employees)
        else:
            await self._reconcile_slack_bots_shared(active_employees)

        # --- Pool capacity alert removed (per_employee mode is deprecated) ---
        # Slot-based provisioning has been replaced by the fixed-bot architecture.
        # Capacity monitoring is no longer needed — each bot type is a single
        # pre-configured Slack app identity.

    # ------------------------------------------------------------------
    # Discord — per-employee (unchanged)
    # ------------------------------------------------------------------

    async def _reconcile_discord_bot(self, emp: Employee) -> None:
        """Start, stop, or leave alone the Discord bot for *emp*."""
        try:
            token = decrypt_discord_token(emp)
        except Exception:
            logger.exception("Failed to decrypt Discord token for employee %s", emp.id)
            if emp.id in self.discord_bots:
                await self._stop_discord_bot(emp.id)
            return

        if token:
            if emp.id not in self.discord_bots:
                await self._start_discord_bot(emp.id, token)
        else:
            if emp.id in self.discord_bots:
                await self._stop_discord_bot(emp.id)

    async def _start_discord_bot(self, emp_id: UUID, token: str) -> None:
        """Create and launch a Discord client for *emp_id*.

        Uses ``wait_until_ready()`` with a timeout to confirm the bot
        successfully connected and cached guilds. Retries with exponential
        backoff on transient errors.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            bot = EmployeeDiscordBot(employee_id=emp_id)
            task = asyncio.create_task(bot.start(token))
            # Register immediately so _stop_discord_bot can clean up on failure
            self.discord_bots[emp_id] = (bot, task)
            logger.info(
                "Starting Discord bot for employee %s (attempt %d/%d)",
                emp_id, attempt, _MAX_RETRIES,
            )

            # Wait for the bot to actually connect and become ready
            try:
                await asyncio.wait_for(bot.wait_until_ready(), timeout=30)
            except TimeoutError:
                logger.error(
                    "Discord bot for employee %s did not become ready within timeout "
                    "(attempt %d/%d)",
                    emp_id, attempt, _MAX_RETRIES,
                )
                await self._stop_discord_bot(emp_id)
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Retrying Discord bot for employee %s in %ds", emp_id, delay,
                    )
                    await asyncio.sleep(delay)
                continue
            except asyncio.CancelledError:
                # The task was cancelled externally — propagate.
                await self._stop_discord_bot(emp_id)
                return
            except Exception as exc:
                logger.error(
                    "Discord bot for employee %s failed to connect: %s "
                    "(attempt %d/%d)",
                    emp_id, exc, attempt, _MAX_RETRIES,
                )
                await self._stop_discord_bot(emp_id)
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                continue

            # Bot is ready — connection confirmed
            logger.info(
                "Discord bot for employee %s connected successfully (attempt %d/%d)",
                emp_id, attempt, _MAX_RETRIES,
            )

            # Record bot connect (best-effort)
            try:
                async with async_session_factory() as s:
                    emp = await s.get(Employee, emp_id)
                    if emp:
                        await record_activity(
                            s, emp.org_id, "agent_conversation",
                            f"Discord bot connected for {emp.name}",
                            employee_id=emp_id, employee_name=emp.name,
                            platform="discord", status="succeeded",
                        )
            except Exception:
                pass

            return

        logger.error(
            "Giving up on Discord bot for employee %s after %d attempts",
            emp_id, _MAX_RETRIES,
        )

    async def _stop_discord_bot(self, emp_id: UUID) -> None:
        entry = self.discord_bots.pop(emp_id, None)
        if entry is None:
            return
        bot, task = entry
        try:
            await bot.close()
        except Exception:
            logger.exception("Error closing Discord client for employee %s", emp_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Discord task error during shutdown for employee %s", emp_id)
        logger.info("Stopped Discord bot for employee %s", emp_id)

    # ------------------------------------------------------------------
    # Slack — shared mode (legacy)
    # ------------------------------------------------------------------

    async def _reconcile_slack_bots_shared(self, active_employees: list[Employee]) -> None:
        """Group active employees by decrypted Slack token and ensure exactly
        one :class:`WorkspaceSlackBot` is running per unique token.
        """
        if not settings.slack_app_token:
            shared_bots: dict[str, WorkspaceSlackBot] = self.slack_bots  # type: ignore[assignment]
            for token in list(shared_bots.keys()):
                await self._stop_workspace_slack_bot(token)
            return

        # Group employees by decrypted bot token
        token_to_employees: dict[str, list[UUID]] = defaultdict(list)
        for emp in active_employees:
            try:
                token = decrypt_slack_token(emp)
            except Exception:
                logger.exception(
                    "Failed to decrypt Slack token for employee %s — skipping", emp.id,
                )
                continue
            if token:
                token_to_employees[token].append(emp.id)

        active_tokens = set(token_to_employees.keys())

        shared_bots: dict[str, WorkspaceSlackBot] = self.slack_bots  # type: ignore[assignment]

        # Stop bots for tokens that are no longer present
        for token in list(shared_bots.keys()):
            if token not in active_tokens:
                await self._stop_workspace_slack_bot(token)

        # Start / update bots for current tokens
        for token, emp_ids in token_to_employees.items():
            if token in shared_bots:
                existing = shared_bots[token]
                existing.employee_ids = emp_ids
                existing._employee_id_set = frozenset(emp_ids)
            else:
                await self._start_workspace_slack_bot(token, emp_ids)

    async def _start_workspace_slack_bot(
        self, token: str, employee_ids: list[UUID],
    ) -> None:
        """Create and connect a single Socket Mode connection for *token*."""
        if not settings.slack_app_token:
            logger.warning("Cannot start Slack bot — SLACK_APP_TOKEN is not set.")
            return

        bot = WorkspaceSlackBot(
            bot_token=token,
            app_token=settings.slack_app_token,
            employee_ids=employee_ids,
        )
        try:
            await bot.connect()
        except Exception:
            logger.exception(
                "Failed to connect Slack Socket Mode (token=...%s)", token[-8:],
            )
            return

        shared_bots: dict[str, WorkspaceSlackBot] = self.slack_bots  # type: ignore[assignment]
        shared_bots[token] = bot
        logger.info(
            "Started Slack bot for token ...%s (%d employees)",
            token[-8:], len(employee_ids),
        )

    async def _stop_workspace_slack_bot(self, token: str) -> None:
        """Disconnect and remove the WorkspaceSlackBot for *token*."""
        shared_bots: dict[str, WorkspaceSlackBot] = self.slack_bots  # type: ignore[assignment]
        bot = shared_bots.pop(token, None)
        if bot is None:
            return
        await bot.disconnect()
        logger.info("Stopped Slack bot for token ...%s", token[-8:])

    # ------------------------------------------------------------------
    # Slack — per-employee mode (Pattern A)
    # ------------------------------------------------------------------

    async def _reconcile_slack_bots_per_employee(
        self, active_employees: list[Employee],
    ) -> None:
        """Per-employee mode is deprecated in favor of fixed bots.

        The ``slack_app_slots`` table and ``SlackAppSlot`` model have been
        removed.  This method is kept as a no-op to avoid crashing if someone
        has ``slack_identity_mode=per_employee`` in their .env — it logs a
        warning and skips reconciliation.
        """
        logger.warning(
            "slack_identity_mode=per_employee is deprecated. "
            "Switch to slack_identity_mode=fixed and configure SLACK_BOT_*_APP_TOKEN "
            "environment variables for each bot type."
        )
        # Stop any running per-employee bots since slots no longer exist
        per_emp_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]
        for emp_id in list(per_emp_bots.keys()):
            await self._stop_employee_slack_bot(emp_id)

    # _reconcile_employee_slack_bot removed — per_employee mode is deprecated.
    # The slot-based reconciliation (emp.slack_slot) no longer applies since
    # the slack_app_slots table was dropped.  Use _reconcile_fixed_slack_bot.

    async def _start_employee_slack_bot(
        self, emp_id: UUID, bot_token: str, app_token: str,
    ) -> None:
        """Create and connect an EmployeeSlackBot for *emp_id*."""
        bot = EmployeeSlackBot(
            employee_id=emp_id,
            bot_token=bot_token,
            app_token=app_token,
        )
        try:
            await bot.connect()
        except Exception:
            logger.exception(
                "Failed to connect EmployeeSlackBot for employee %s", emp_id,
            )
            return

        per_emp_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]
        per_emp_bots[emp_id] = bot
        logger.info("Started EmployeeSlackBot for employee %s", emp_id)

        # Record bot connect (best-effort)
        try:
            async with async_session_factory() as s:
                emp = await s.get(Employee, emp_id)
                if emp:
                    await record_activity(
                        s, emp.org_id, "agent_conversation",
                        f"Slack bot connected for {emp.name}",
                        employee_id=emp_id, employee_name=emp.name,
                        platform="slack", status="succeeded",
                    )
        except Exception:
            pass

    async def _stop_employee_slack_bot(self, emp_id: UUID) -> None:
        """Disconnect and remove the EmployeeSlackBot for *emp_id*."""
        per_emp_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]
        bot = per_emp_bots.pop(emp_id, None)
        if bot is None:
            return
        await bot.disconnect()
        logger.info("Stopped EmployeeSlackBot for employee %s", emp_id)

        # Record bot disconnect (best-effort)
        try:
            async with async_session_factory() as s:
                emp = await s.get(Employee, emp_id)
                if emp:
                    await record_activity(
                        s, emp.org_id, "agent_conversation",
                        f"Slack bot disconnected for {emp.name}",
                        employee_id=emp_id, employee_name=emp.name,
                        platform="slack", status="succeeded",
                    )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Slack — fixed mode (named bots)
    # ------------------------------------------------------------------

    async def _reconcile_slack_bots_fixed(
        self, active_employees: list[Employee],
    ) -> None:
        """One :class:`EmployeeSlackBot` per active employee with a Slack token.

        The app_token comes from the fixed bot registry (keyed by employee_type)
        rather than a DB slot.  The bot_token is org-specific (from OAuth).
        """
        per_emp_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]

        # Collect active employee IDs that have valid Slack config
        active_slack_ids: set[UUID] = set()
        for emp in active_employees:
            if emp.slack_token_enc is None:
                continue
            # Must have a fixed bot configured for this employee type
            if not emp.employee_type:
                logger.debug("Employee %s has no employee_type — skipping", emp.id)
                continue
            fixed_bot = get_fixed_bot(emp.employee_type)
            if fixed_bot is None or not fixed_bot.app_token:
                logger.debug(
                    "Employee %s type '%s' has no fixed bot app_token — skipping",
                    emp.id, emp.employee_type,
                )
                continue
            active_slack_ids.add(emp.id)

        # Stop bots for employees no longer active / without Slack
        for emp_id in list(per_emp_bots.keys()):
            if emp_id not in active_slack_ids:
                await self._stop_employee_slack_bot(emp_id)

        # Start / reconcile bots for active employees
        for emp in active_employees:
            if emp.id not in active_slack_ids:
                continue
            await self._reconcile_fixed_slack_bot(emp)

    async def _reconcile_fixed_slack_bot(self, emp: Employee) -> None:
        """Start, stop, or leave alone the EmployeeSlackBot for *emp* (fixed mode)."""
        per_emp_bots: dict[UUID, EmployeeSlackBot] = self.slack_bots  # type: ignore[assignment]

        try:
            bot_token = decrypt_slack_token(emp)
        except Exception:
            logger.exception("Failed to decrypt Slack token for employee %s", emp.id)
            if emp.id in per_emp_bots:
                await self._stop_employee_slack_bot(emp.id)
            return

        if bot_token is None or not emp.employee_type:
            if emp.id in per_emp_bots:
                await self._stop_employee_slack_bot(emp.id)
            return

        fixed_bot = get_fixed_bot(emp.employee_type)
        if fixed_bot is None or not fixed_bot.app_token:
            if emp.id in per_emp_bots:
                await self._stop_employee_slack_bot(emp.id)
            return

        app_token = fixed_bot.app_token

        if emp.id in per_emp_bots:
            existing = per_emp_bots[emp.id]
            if existing.bot_token != bot_token or existing.app_token != app_token:
                logger.info("Slack credentials changed for employee %s — restarting bot", emp.id)
                await self._stop_employee_slack_bot(emp.id)
            else:
                # Bot already running with correct credentials
                return

        await self._start_employee_slack_bot(emp.id, bot_token, app_token)
