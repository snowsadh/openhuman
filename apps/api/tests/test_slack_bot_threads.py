from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.gateway.slack_bot import WorkspaceSlackBot


@pytest.fixture()
def mock_app():
    with (
        patch("app.gateway.slack_bot.AsyncApp") as mock_app_cls,
        patch("app.gateway.slack_bot.AsyncSocketModeHandler") as mock_handler_cls,
    ):
        mock_app_inst = MagicMock()
        mock_app_cls.return_value = mock_app_inst
        mock_handler_inst = MagicMock()
        mock_handler_cls.return_value = mock_handler_inst
        yield mock_app_inst


@pytest.mark.anyio
async def test_handle_message_dm(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot._process_slack_message = AsyncMock()

    event = {
        "text": "hello",
        "channel": "D123",
        "channel_type": "im",
        "ts": "100.1",
    }
    say = AsyncMock()

    await bot.handle_message(event, say)
    bot._process_slack_message.assert_awaited_once_with(event, say)


@pytest.mark.anyio
async def test_handle_message_thread_no_bot_participation(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot._process_slack_message = AsyncMock()
    bot.bot_user_id = "U_BOT"

    # Mock conversation replies where bot DID NOT participate
    bot.app.client.conversations_replies = AsyncMock(return_value={
        "messages": [
            {"user": "U_USER1", "text": "hello"},
            {"user": "U_USER2", "text": "howdy"},
        ]
    })

    event = {
        "text": "reply in thread",
        "channel": "C123",
        "thread_ts": "100.0",
        "ts": "100.2",
    }
    say = AsyncMock()

    await bot.handle_message(event, say)
    bot._process_slack_message.assert_not_awaited()
    bot.app.client.conversations_replies.assert_awaited_once_with(
        channel="C123",
        ts="100.0",
        limit=50,
    )


@pytest.mark.anyio
async def test_handle_message_thread_with_bot_participation(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot._process_slack_message = AsyncMock()
    bot.bot_user_id = "U_BOT"

    # Mock conversation replies where bot DID participate
    bot.app.client.conversations_replies = AsyncMock(return_value={
        "messages": [
            {"user": "U_USER1", "text": "hello bot"},
            {"user": "U_BOT", "text": "I am here!"},
            {"user": "U_USER1", "text": "reply without mention"},
        ]
    })

    event = {
        "text": "reply without mention",
        "channel": "C123",
        "thread_ts": "100.0",
        "ts": "100.2",
    }
    say = AsyncMock()

    await bot.handle_message(event, say)
    bot._process_slack_message.assert_awaited_once_with(event, say)


@pytest.mark.anyio
async def test_handle_message_thread_with_direct_mention_skipped(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot._process_slack_message = AsyncMock()
    bot.bot_user_id = "U_BOT"

    # If the message contains a direct mention, it should be skipped in handle_message
    # (because handle_mention will catch and process it instead, avoiding double-posting).
    event = {
        "text": "<@U_BOT> direct question",
        "channel": "C123",
        "thread_ts": "100.0",
        "ts": "100.2",
    }
    say = AsyncMock()

    await bot.handle_message(event, say)
    bot._process_slack_message.assert_not_awaited()
    # It shouldn't even check history
    bot.app.client.conversations_replies.assert_not_called()
