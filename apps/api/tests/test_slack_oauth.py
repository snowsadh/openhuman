from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from app.core.config import settings
from app.gateway.slack_oauth import _SLACK_BOT_SCOPES, router as slack_oauth_router


def _make_state_token(employee_id: str, org_id: str, redirect_to: str | None = None) -> str:
    """Create a signed OAuth state token for tests."""
    secret = settings.encryption_key or settings.jwt_secret_key or "test-secret"
    serializer = URLSafeTimedSerializer(secret, salt="slack-oauth-state")
    payload: dict[str, str] = {
        "employee_id": employee_id,
        "org_id": org_id,
    }
    if redirect_to:
        payload["redirect_to"] = redirect_to
    return serializer.dumps(payload)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    test_app = FastAPI()
    test_app.include_router(slack_oauth_router)
    with TestClient(test_app) as test_client:
        yield test_client


def test_slack_install_scopes_include_file_uploads() -> None:
    """Slack installs must request file scopes so generated PDFs can attach in chat."""
    assert "files:write" in _SLACK_BOT_SCOPES
    assert "files:read" in _SLACK_BOT_SCOPES


@pytest.mark.anyio
async def test_slack_install_invalid_uuids(client: TestClient) -> None:
    with patch("app.gateway.slack_oauth.settings") as mock_settings:
        mock_settings.slack_client_id = "test-client-id"
        mock_settings.slack_oauth_redirect_uri = "https://example.com/callback"
        mock_settings.slack_identity_mode = "shared"
        mock_settings.frontend_url = "http://localhost:3000"

        response = client.get(
            "/api/slack/install?employee_id=emp-1&org_id=org-1",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "slack=error" in response.headers["location"]
        assert "Invalid+employee+or+organization+ID." in response.headers["location"]
        assert "employee_id=emp-1" in response.headers["location"]


@pytest.mark.anyio
async def test_slack_install_custom_redirect_to(client: TestClient) -> None:
    employee_id = str(uuid4())
    org_id = str(uuid4())
    custom_redirect = "http://localhost:8501/custom-dashboard"

    with (
        patch("app.gateway.slack_oauth.settings") as mock_settings,
        patch("app.gateway.slack_oauth.async_session_factory") as mock_session_factory,
    ):
        mock_settings.slack_client_id = "test-client-id"
        mock_settings.slack_oauth_redirect_uri = "https://example.com/callback"
        mock_settings.slack_identity_mode = "shared"
        mock_settings.encryption_key = ""
        mock_settings.jwt_secret_key = "test-secret"

        mock_session = MagicMock()
        mock_emp = MagicMock()
        mock_emp.id = employee_id
        mock_emp.org_id = org_id
        mock_session.scalar = AsyncMock(return_value=mock_emp)
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        response = client.get(
            f"/api/slack/install?employee_id={employee_id}&org_id={org_id}"
            f"&redirect_to={custom_redirect}",
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert "slack.com/oauth/v2/authorize" in location
        assert "client_id=test-client-id" in location

        # Extract and decode the state parameter
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(location)
        state_param = parse_qs(parsed.query)["state"][0]

        secret = mock_settings.encryption_key or mock_settings.jwt_secret_key
        serializer = URLSafeTimedSerializer(secret, salt="slack-oauth-state")
        decoded = serializer.loads(state_param)
        assert decoded["employee_id"] == employee_id
        assert decoded["org_id"] == org_id
        assert decoded["redirect_to"] == custom_redirect


@pytest.mark.anyio
async def test_slack_callback_redirects_to_custom_url(client: TestClient) -> None:
    employee_id = str(uuid4())
    org_id = str(uuid4())
    custom_redirect = "http://localhost:8501/custom-dashboard"

    with (
        patch("app.gateway.slack_oauth.settings") as mock_settings,
        patch("app.core.config.settings") as mock_core_settings,
        patch("app.gateway.slack_oauth.async_session_factory") as mock_session_factory,
        patch("app.gateway.slack_oauth.AsyncWebClient") as mock_slack_client,
        patch("app.gateway.slack_oauth.encrypt_token", return_value="encrypted-mock-token"),
    ):
        mock_settings.slack_client_id = "test-client-id"
        mock_settings.slack_client_secret = "test-client-secret"
        mock_settings.slack_oauth_redirect_uri = "https://example.com/callback"
        mock_settings.slack_identity_mode = "shared"
        mock_settings.encryption_key = ""
        mock_settings.jwt_secret_key = "test-secret"
        mock_core_settings.encryption_key = ""
        mock_core_settings.jwt_secret_key = "test-secret"

        # Create state token using the same mocked settings
        secret = mock_core_settings.encryption_key or mock_core_settings.jwt_secret_key or "test-secret"
        serializer = URLSafeTimedSerializer(secret, salt="slack-oauth-state")
        payload = {
            "employee_id": employee_id,
            "org_id": org_id,
        }
        if custom_redirect:
            payload["redirect_to"] = custom_redirect
        state_token = serializer.dumps(payload)

        # Mock Slack OAuth Response
        mock_client_inst = MagicMock()
        mock_client_inst.oauth_v2_access = AsyncMock(
            return_value={
                "ok": True,
                "access_token": "xoxb-mock-bot-token",
                "team": {"name": "Test Team"},
            }
        )
        mock_slack_client.return_value = mock_client_inst

        # Mock DB session
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_emp = MagicMock()
        mock_session.scalar = AsyncMock(return_value=mock_emp)
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        response = client.get(
            f"/api/slack/oauth/callback?code=mock-code&state={state_token}",
            follow_redirects=False,
        )

        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith(custom_redirect)
        assert "slack=connected" in location
        assert f"employee_id={employee_id}" in location
