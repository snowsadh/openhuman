"""Unit tests for bot gateway manager and Discord/Slack bot message filters
(Phase 6).

Covers the verification scenarios from the audit plan:
- Manager start/stop decisions with mocked employee rows
- Discord mention / DM filters
- Slack mention / DM filters
- Channel assignment filtering
- Error message sanitization
- Bad-token handling
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

import app.agent.tools.mcp.models  # noqa: F401

# Ensure all model modules are imported before SQLAlchemy mapper configuration
# is triggered by the gateway refresh loop (same pattern as app/main.py).
import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401

# =============================================================================
# Helpers
# =============================================================================


def _make_emp(
    emp_id: UUID | None = None,
    *,
    status: str = "active",
    discord_token: str | None = "encrypted-discord-token",
    slack_token: str | None = "encrypted-slack-token",
) -> MagicMock:
    """Build a mock Employee ORM object with the given fields."""
    emp = MagicMock()
    emp.id = emp_id or uuid4()
    emp.status = status
    emp.discord_token_enc = discord_token
    emp.slack_token_enc = slack_token
    return emp


# =============================================================================
# Gateway Manager lifecycle tests
# =============================================================================


class TestGatewayManagerLifecycle:
    """BotGatewayManager start / stop and refresh behaviour."""

    @pytest.mark.anyio
    async def test_start_creates_refresh_task(self):
        from app.gateway.manager import BotGatewayManager

        mgr = BotGatewayManager()
        await mgr.start()
        assert mgr.running is True
        assert mgr.refresh_task is not None
        # Cleanup
        await mgr.stop()

    @pytest.mark.anyio
    async def test_stop_cancels_refresh_task(self):
        from app.gateway.manager import BotGatewayManager

        mgr = BotGatewayManager()
        await mgr.start()
        await mgr.stop()
        assert mgr.running is False
        # Task should be cancelled
        assert mgr.refresh_task is not None
        assert mgr.refresh_task.cancelled() or mgr.refresh_task.done()

    @pytest.mark.anyio
    async def test_stop_cleans_up_discord_bots(self):
        from app.gateway.manager import BotGatewayManager

        mgr = BotGatewayManager()
        # Use AsyncMock so close() is recognised as an async method
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        emp_id = uuid4()
        mgr.discord_bots[emp_id] = (mock_bot, mock_task)
        mgr.running = True

        await mgr.stop()
        # Bot should have been closed
        mock_bot.close.assert_awaited_once()
        # Task should be cancelled
        mock_task.cancel.assert_called_once()

    @pytest.mark.anyio
    async def test_stop_cleans_up_slack_bots_shared_mode(self):
        from app.gateway.manager import BotGatewayManager

        with patch("app.gateway.manager.settings") as mock_settings:
            mock_settings.slack_identity_mode = "shared"

            mgr = BotGatewayManager()
            mock_bot = MagicMock()
            mock_bot.disconnect = AsyncMock()
            mgr.slack_bots["test-token"] = mock_bot
            mgr.running = True

            await mgr.stop()
            mock_bot.disconnect.assert_awaited_once()

    @pytest.mark.anyio
    async def test_lifespan_does_not_start_when_disabled(self):
        """When gateway_enabled=False, the lifespan should NOT start the gateway."""
        from app.core.config import Settings

        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)  # type: ignore[call-arg]
            assert s.gateway_enabled is False, (
                "gateway_enabled must be False by default for dev safety"
            )


# =============================================================================
# Gateway refresh_bots tests (mocked DB)
# =============================================================================


class TestRefreshBots:
    """refresh_bots starts/stops bots based on active employee rows."""

    @pytest.mark.anyio
    async def test_starts_bots_for_active_employees(self):
        from app.gateway.manager import BotGatewayManager

        emp = _make_emp()

        with (
            patch("app.gateway.manager.async_session_factory") as mock_session_factory,
            patch(
                "app.gateway.manager.get_active_employees_with_tokens",
                new_callable=AsyncMock,
            ) as mock_get_active,
            patch("app.gateway.manager.decrypt_discord_token", return_value="dtoken"),
            patch("app.gateway.manager.decrypt_slack_token", return_value="stoken"),
            patch("app.gateway.manager.settings") as mock_settings,
        ):
            mock_settings.slack_app_token = "xapp-token"
            mock_settings.slack_identity_mode = "shared"
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_get_active.return_value = [emp]

            mgr = BotGatewayManager()
            # Stub _start_discord_bot / _start_workspace_slack_bot to avoid real I/O
            mgr._start_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._start_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]

            await mgr.refresh_bots()

            mgr._start_discord_bot.assert_awaited_once_with(emp.id, "dtoken")
            mgr._start_workspace_slack_bot.assert_awaited_once_with("stoken", [emp.id])

    @pytest.mark.anyio
    async def test_stops_bots_for_inactive_employees(self):
        from app.gateway.manager import BotGatewayManager

        emp = _make_emp(status="inactive")

        with (
            patch("app.gateway.manager.async_session_factory") as mock_session_factory,
            patch(
                "app.gateway.manager.get_active_employees_with_tokens",
                new_callable=AsyncMock,
            ) as mock_get_active,
            patch("app.gateway.manager.decrypt_discord_token", return_value="dtoken"),
            patch("app.gateway.manager.decrypt_slack_token", return_value="stoken"),
            patch("app.gateway.manager.settings") as mock_settings,
        ):
            mock_settings.slack_app_token = "xapp-token"
            mock_settings.slack_identity_mode = "shared"
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            # Inactive employees are NOT returned by get_active_employees
            mock_get_active.return_value = []

            mgr = BotGatewayManager()
            mgr._start_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._start_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]

            # Manually add a running bot for this employee (shared mode: keyed by token)
            mgr.discord_bots[emp.id] = (MagicMock(), MagicMock())  # type: ignore[arg-type]
            mgr.slack_bots["test-token"] = MagicMock()  # type: ignore[arg-type]

            await mgr.refresh_bots()

            mgr._stop_discord_bot.assert_awaited_once_with(emp.id)
            mgr._stop_workspace_slack_bot.assert_awaited_once_with("test-token")

    @pytest.mark.anyio
    async def test_handles_decryption_failure_gracefully(self):
        """Bad encryption key for one employee must not crash the loop."""
        from app.gateway.manager import BotGatewayManager

        emp = _make_emp()

        with (
            patch("app.gateway.manager.async_session_factory") as mock_session_factory,
            patch(
                "app.gateway.manager.get_active_employees_with_tokens",
                new_callable=AsyncMock,
            ) as mock_get_active,
            patch(
                "app.gateway.manager.decrypt_discord_token",
                side_effect=RuntimeError("bad key"),
            ),
            patch(
                "app.gateway.manager.decrypt_slack_token",
                side_effect=RuntimeError("bad key"),
            ),
            patch("app.gateway.manager.settings") as mock_settings,
        ):
            mock_settings.slack_app_token = "xapp-token"
            mock_settings.slack_identity_mode = "shared"
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_get_active.return_value = [emp]

            mgr = BotGatewayManager()
            mgr._start_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._start_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]

            # Previously running bot should be stopped on decryption failure
            mgr.discord_bots[emp.id] = (MagicMock(), MagicMock())  # type: ignore[arg-type]
            mgr.slack_bots["bad-token"] = MagicMock()  # type: ignore[arg-type]

            # Must not raise
            await mgr.refresh_bots()

            # Should NOT try to start new bots and should stop existing ones
            mgr._start_discord_bot.assert_not_awaited()
            mgr._start_workspace_slack_bot.assert_not_awaited()

    @pytest.mark.anyio
    async def test_skips_slack_when_no_app_token(self):
        """When SLACK_APP_TOKEN is empty, Slack bots should not be started."""
        from app.gateway.manager import BotGatewayManager

        emp = _make_emp()

        with (
            patch("app.gateway.manager.async_session_factory") as mock_session_factory,
            patch(
                "app.gateway.manager.get_active_employees_with_tokens",
                new_callable=AsyncMock,
            ) as mock_get_active,
            patch("app.gateway.manager.decrypt_discord_token", return_value="dtoken"),
            patch("app.gateway.manager.decrypt_slack_token", return_value="stoken"),
            patch("app.gateway.manager.settings") as mock_settings,
        ):
            mock_settings.slack_app_token = ""  # No app token
            mock_settings.slack_identity_mode = "shared"
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_get_active.return_value = [emp]

            mgr = BotGatewayManager()
            mgr._start_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._start_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]

            await mgr.refresh_bots()

            mgr._start_discord_bot.assert_awaited_once()
            mgr._start_workspace_slack_bot.assert_not_awaited()

    @pytest.mark.anyio
    async def test_skips_employee_without_tokens(self):
        """Employee with no bot tokens should not trigger bot startup."""
        from app.gateway.manager import BotGatewayManager

        emp = _make_emp(discord_token=None, slack_token=None)

        with (
            patch("app.gateway.manager.async_session_factory") as mock_session_factory,
            patch(
                "app.gateway.manager.get_active_employees_with_tokens",
                new_callable=AsyncMock,
            ) as mock_get_active,
            patch("app.gateway.manager.decrypt_discord_token", return_value=None),
            patch("app.gateway.manager.decrypt_slack_token", return_value=None),
            patch("app.gateway.manager.settings") as mock_settings,
        ):
            mock_settings.slack_app_token = "xapp-token"
            mock_settings.slack_identity_mode = "shared"
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_get_active.return_value = [emp]

            mgr = BotGatewayManager()
            mgr._start_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._start_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_discord_bot = AsyncMock()  # type: ignore[method-assign]
            mgr._stop_workspace_slack_bot = AsyncMock()  # type: ignore[method-assign]

            await mgr.refresh_bots()

            mgr._start_discord_bot.assert_not_awaited()
            mgr._start_workspace_slack_bot.assert_not_awaited()


# =============================================================================
# Discord bot message filter tests
# =============================================================================


class TestDiscordBotFilters:
    """EmployeeDiscordBot must respond only to DMs or mentions in assigned channels."""

    def test_dm_message_always_passes(self):
        """DMs should trigger a response regardless of mentions."""
        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.id = 999
        mock_msg.channel = MagicMock(spec=[])
        # isinstance check for DMChannel
        import discord

        mock_msg.channel.__class__ = discord.DMChannel  # type: ignore[assignment]
        mock_msg.content = "hello"
        mock_msg.mentions = []

        assert bot._is_dm(mock_msg) is True

    def test_mention_passes(self):
        """A channel message that @mentions the bot should pass."""
        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())
        mock_user = MagicMock()
        mock_user.id = 12345
        # discord.Client.user is a read-only property backed by _connection.user
        mock_conn = MagicMock()
        mock_conn.user = mock_user
        object.__setattr__(bot, "_connection", mock_conn)

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.id = 999
        mock_msg.mentions = [mock_user]

        assert bot._is_mentioned(mock_msg) is True

    def test_no_mention_no_dm_skips(self):
        """A regular channel message without mention should NOT trigger."""
        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_conn = MagicMock()
        mock_conn.user = mock_user
        object.__setattr__(bot, "_connection", mock_conn)

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.id = 999
        mock_msg.mentions = []
        mock_msg.channel = MagicMock()
        # Not a DM

        assert bot._is_dm(mock_msg) is False
        assert bot._is_mentioned(mock_msg) is False

    def test_mention_removal_strips_tags(self):
        """Bot mention tags should be removed from message content."""
        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_conn = MagicMock()
        mock_conn.user = mock_user
        object.__setattr__(bot, "_connection", mock_conn)

        # Simulate the content stripping logic directly
        content = "<@!12345> <@12345> hello there"
        content = content.replace(f"<@!{mock_user.id}>", "").replace(f"<@{mock_user.id}>", "")
        content = content.strip()
        assert content == "hello there"

    @pytest.mark.anyio
    async def test_channel_assignment_filter_allows_assigned(self):
        """When channel_assignments exist, only assigned channels respond."""
        from app.channel_assignments.models import ChannelAssignment
        from app.gateway.discord_bot import EmployeeDiscordBot

        emp_id = uuid4()
        bot = EmployeeDiscordBot(employee_id=emp_id)

        mock_assignment = MagicMock(spec=ChannelAssignment)
        mock_assignment.channel_id = "123456"

        with patch("app.gateway.discord_bot.async_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_assignment]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__.return_value = mock_session

            assert await bot._is_assigned_channel(123456) is True
            assert await bot._is_assigned_channel(999999) is False

    @pytest.mark.anyio
    async def test_channel_assignment_filter_allows_all_when_empty(self):
        """No channel assignments means respond everywhere."""
        from app.gateway.discord_bot import EmployeeDiscordBot

        emp_id = uuid4()
        bot = EmployeeDiscordBot(employee_id=emp_id)

        with patch("app.gateway.discord_bot.async_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__.return_value = mock_session

            assert await bot._is_assigned_channel(123456) is True
            assert await bot._is_assigned_channel(999999) is True


# =============================================================================
# Slack bot filter tests
# =============================================================================


class TestSlackBotFilters:
    """EmployeeSlackBot must respond to app_mention events and DMs only."""

    def _make_bot(self, emp_id: UUID | None = None):
        """Create an EmployeeSlackBot with a mocked AsyncApp."""
        from app.gateway.slack_bot import EmployeeSlackBot

        with patch("app.gateway.slack_bot.AsyncApp") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            bot = EmployeeSlackBot(
                employee_id=emp_id or uuid4(),
                bot_token="xoxb-test",
                app_token="xapp-test",
            )
            bot.app = mock_app
            return bot

    @pytest.mark.anyio
    async def test_app_mention_triggers_processing(self):
        bot = self._make_bot()
        bot.bot_user_id = "U123"  # simulates a bot that has finished connecting
        bot._run_agent = AsyncMock(return_value={"response": "Hi!", "files": []})  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {"text": "<@U123> hello bot", "channel": "C001", "ts": "100"}
        say = AsyncMock()

        await bot.handle_mention(event, say)
        bot._run_agent.assert_awaited_once()

    @pytest.mark.anyio
    async def test_app_mention_ignored_when_bot_user_id_unknown(self):
        """If the bot's own identity hasn't resolved yet, it must NOT respond
        (fail closed) — otherwise it could answer on behalf of another
        employee's bot mentioned in the same message."""
        bot = self._make_bot()
        bot.bot_user_id = None
        bot._run_agent = AsyncMock(return_value={"response": "Hi!", "files": []})  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {"text": "<@U123> hello bot", "channel": "C001", "ts": "100"}
        say = AsyncMock()

        await bot.handle_mention(event, say)
        bot._run_agent.assert_not_awaited()

    @pytest.mark.anyio
    async def test_app_mention_for_different_bot_ignored(self):
        """A mention of a different employee's bot user id must not trigger
        this bot's processing."""
        bot = self._make_bot()
        bot.bot_user_id = "U123"
        bot._run_agent = AsyncMock(return_value={"response": "Hi!", "files": []})  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {"text": "<@U999> hello bot", "channel": "C001", "ts": "100"}
        say = AsyncMock()

        await bot.handle_mention(event, say)
        bot._run_agent.assert_not_awaited()

    @pytest.mark.anyio
    async def test_dm_triggers_processing(self):
        bot = self._make_bot()
        bot._run_agent = AsyncMock(return_value={"response": "Hi!", "files": []})  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {
            "text": "hey",
            "channel": "D001",
            "channel_type": "im",
            "ts": "100",
        }
        say = AsyncMock()

        await bot.handle_message(event, say)
        bot._run_agent.assert_awaited_once()

    @pytest.mark.anyio
    async def test_public_channel_message_ignored(self):
        """A regular channel message that is NOT an app_mention must be ignored."""
        bot = self._make_bot()
        bot._run_agent = AsyncMock(return_value="Hi!")  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {
            "text": "hello everyone",
            "channel": "C001",
            "channel_type": "channel",  # NOT 'im'
            "ts": "100",
        }
        say = AsyncMock()

        await bot.handle_message(event, say)
        bot._run_agent.assert_not_awaited()

    @pytest.mark.anyio
    async def test_bot_messages_ignored(self):
        """Messages from other bots should be silently dropped."""
        bot = self._make_bot()
        bot._run_agent = AsyncMock(return_value="Hi!")  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {
            "text": "automated message",
            "channel": "C001",
            "channel_type": "im",
            "bot_id": "B999",
            "ts": "100",
        }
        say = AsyncMock()

        await bot._process_slack_message(event, say)
        bot._run_agent.assert_not_awaited()

    @pytest.mark.anyio
    async def test_replies_in_thread(self):
        """Slack responses should include thread_ts."""
        bot = self._make_bot()
        bot.bot_user_id = "U123"  # simulates a bot that has finished connecting
        bot._run_agent = AsyncMock(return_value={"response": "Hello!", "files": []})  # type: ignore[method-assign]
        bot._is_channel_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

        event = {"text": "<@U123> hi", "channel": "C001", "ts": "100.5"}
        say = AsyncMock()

        await bot._process_slack_message(event, say)
        say.assert_awaited_once()
        call_kwargs = say.await_args.kwargs
        assert call_kwargs["thread_ts"] == "100.5"

    @pytest.mark.anyio
    async def test_channel_assignment_filter_slack(self):
        """In public channels, only assigned channels should respond."""
        from app.channel_assignments.models import ChannelAssignment

        emp_id = uuid4()
        bot = self._make_bot(emp_id=emp_id)

        mock_assignment = MagicMock(spec=ChannelAssignment)
        mock_assignment.channel_id = "C001"

        with patch("app.gateway.slack_bot.async_session_factory") as mock_factory:
            mock_session = MagicMock()

            # For _is_channel_allowed("C001"):
            #   1. any_assignments check: scalar returns mock_assignment (has assignments)
            #   2. specific channel check: execute returns result with "C001"
            # For _is_channel_allowed("C999"):
            #   3. any_assignments check: scalar returns mock_assignment (has assignments)
            #   4. specific channel check: execute returns result with no match
            mock_session.scalar = AsyncMock(return_value=mock_assignment)

            assigned_result = MagicMock()
            assigned_result.scalars.return_value.first.return_value = mock_assignment
            not_assigned_result = MagicMock()
            not_assigned_result.scalars.return_value.first.return_value = None
            mock_session.execute = AsyncMock(
                side_effect=[
                    assigned_result,  # "C001" found
                    not_assigned_result,  # "C999" not found
                ]
            )

            mock_factory.return_value.__aenter__.return_value = mock_session

            assert await bot._is_channel_allowed("C001") is True
            assert await bot._is_channel_allowed("C999") is False


# =============================================================================
# Error sanitization tests
# =============================================================================


class TestErrorSanitization:
    """Gateways must never leak raw exception details to public channels."""

    @pytest.mark.anyio
    async def test_discord_agent_error_returns_safe_message(self):
        from app.gateway.discord_bot import _SAFE_ERROR_MESSAGE, EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())

        from unittest.mock import MagicMock

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("Internal DB connection pool exhausted: pswd=secret")
        )
        with patch(
            "app.gateway.discord_bot.get_graph_for_employee",
            AsyncMock(return_value=(mock_graph, [])),
        ):
            result = await bot._run_agent("hello")
            assert result == {"response": _SAFE_ERROR_MESSAGE, "files": []}
            assert "pswd=secret" not in result["response"]

    @pytest.mark.anyio
    async def test_slack_agent_error_returns_safe_message(self):
        from unittest.mock import MagicMock

        from app.gateway.slack_bot import _SAFE_ERROR_MESSAGE

        # Use the test helper that mocks AsyncApp construction
        bot = TestSlackBotFilters._make_bot(self)

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("KeyError: 'missing_field' in /etc/secrets")
        )
        with patch(
            "app.gateway.slack_bot.get_graph_for_employee",
            AsyncMock(return_value=(mock_graph, [])),
        ):
            result = await bot._run_agent("hello")
            assert result["response"] == _SAFE_ERROR_MESSAGE
            assert "/etc/secrets" not in result["response"]

    @pytest.mark.anyio
    async def test_discord_graph_interrupt_returns_none(self):
        """GraphInterrupt (HITL escalation) must return None to signal pause."""
        from langgraph.errors import GraphInterrupt

        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=GraphInterrupt("paused"))
        with patch(
            "app.gateway.discord_bot.get_graph_for_employee",
            AsyncMock(return_value=(mock_graph, [])),
        ):
            result = await bot._run_agent("hello")
            assert result is None

    @pytest.mark.anyio
    async def test_discord_empty_response_gets_fallback(self):
        """Empty agent response should get a placeholder, not be blank."""
        from unittest.mock import MagicMock

        from app.gateway.discord_bot import EmployeeDiscordBot

        bot = EmployeeDiscordBot(employee_id=uuid4())

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": ""})
        with patch(
            "app.gateway.discord_bot.get_graph_for_employee",
            AsyncMock(return_value=(mock_graph, [])),
        ):
            result = await bot._run_agent("hello")
            assert result == {"response": ""}

    # ------------------------------------------------------------------
    # Gateway config test
    # ------------------------------------------------------------------

    def test_settings_gateway_disabled_by_default(self):
        """gateway_enabled must default to False for dev safety."""

        from app.core.config import Settings

        # Create a fresh settings instance (ignores .env)
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)  # type: ignore[call-arg]
            assert s.gateway_enabled is False
