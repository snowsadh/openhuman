import base64
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from slack_sdk.errors import SlackApiError

from app.gateway.slack_bot import WorkspaceSlackBot


@pytest.fixture()
def mock_app():
    with (
        patch("app.gateway.slack_bot.AsyncApp") as mock_app_cls,
        patch("app.gateway.slack_bot.AsyncSocketModeHandler") as mock_handler_cls,
    ):
        mock_app_inst = MagicMock()
        mock_app_cls.return_value = mock_app_inst
        mock_handler_cls.return_value = MagicMock()
        yield mock_app_inst


def _slack_api_error(error_code: str) -> SlackApiError:
    response = MagicMock()
    response.get.side_effect = lambda key, default=None: {"error": error_code}.get(key, default)
    return SlackApiError(message=error_code, response=response)


@pytest.mark.anyio
async def test_send_files_reports_missing_scope_error(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot.app.client.files_upload_v2 = AsyncMock(side_effect=_slack_api_error("missing_scope"))

    failed = await bot._send_files(
        channel="C123",
        files=[{"filename": "dummy.pdf", "data": base64.b64encode(b"content").decode()}],
        thread_ts="100.0",
    )

    assert failed == [("dummy.pdf", "missing_scope")]


@pytest.mark.anyio
async def test_send_files_success_reports_no_failures(mock_app) -> None:
    bot = WorkspaceSlackBot(
        bot_token="xoxb-test",
        app_token="xapp-test",
        employee_ids=[uuid4()],
    )
    bot.app.client.files_upload_v2 = AsyncMock(return_value={"ok": True})

    failed = await bot._send_files(
        channel="C123",
        files=[{"filename": "dummy.pdf", "data": base64.b64encode(b"content").decode()}],
        thread_ts="100.0",
    )

    assert failed == []


def test_file_upload_failure_message_scope_error_suggests_reconnect() -> None:
    employee_id = uuid4()
    message = WorkspaceSlackBot._file_upload_failure_message(
        [("dummy.pdf", "missing_scope")],
        employee_id,
    )

    assert "dummy.pdf" in message
    assert "reconnect" in message.lower() or "Reconnect" in message
    assert str(employee_id) in message


def test_file_upload_failure_message_other_error_no_reconnect_claim() -> None:
    message = WorkspaceSlackBot._file_upload_failure_message(
        [("dummy.pdf", "invalid_channel")],
        uuid4(),
    )

    assert "dummy.pdf" in message
    assert "invalid_channel" in message
    assert "reconnect" not in message.lower()
