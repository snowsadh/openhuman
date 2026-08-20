from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import anyio
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401
import app.agent.tools.mcp.models  # noqa: F401
from app.auth.models import User
from app.auth.router import router as auth_router
from app.core.database import get_db
from app.organizations.models import Organization

# Make sure we have a valid JWT secret for tests
import app.core.config
app.core.config.settings.jwt_secret_key = "test-jwt-secret-key-for-tests"


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}"
    engine = create_async_engine(database_url)

    @event.listens_for(engine.sync_engine, "connect")
    def register_uuid_function(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def prepare_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(Organization.__table__.create)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(auth_router)
    test_app.dependency_overrides[get_db] = override_get_db

    anyio.run(prepare_database)
    with TestClient(test_app) as test_client:
        yield test_client

    anyio.run(engine.dispose)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_get_token(client: TestClient, email: str, password: str, name: str) -> str:
    """Register a new user and return the JWT access token."""
    resp = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_me_rejects_missing_token(client: TestClient) -> None:
    """Without a Bearer token the /me endpoint returns 401."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token(client: TestClient) -> None:
    """With an invalid / expired token the /me endpoint returns 401."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_register_and_me_returns_user(client: TestClient) -> None:
    """Register a user, then call /me with the returned token to get the profile."""
    email = "ada@example.com"
    name = "Ada Lovelace"

    token = _register_and_get_token(client, email, "securepass123", name)

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    user_payload = response.json()
    assert user_payload["email"] == email
    assert user_payload["name"] == name
    assert user_payload["is_active"] is True
    assert "password_hash" not in user_payload
    assert "clerk_id" not in user_payload


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    """Registering the same email twice returns 409."""
    _register_and_get_token(client, "dup@example.com", "pass123", "First")
    resp = client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "password": "pass123",
        "name": "Second",
    })
    assert resp.status_code == 409


def test_login_with_valid_credentials(client: TestClient) -> None:
    """Login succeeds with the password used at registration."""
    email = "login@example.com"
    password = "mypassword"
    name = "Login User"

    _register_and_get_token(client, email, password, name)

    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token is not None

    # Verify /me works with login token
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


def test_login_with_wrong_password(client: TestClient) -> None:
    """Login fails with an incorrect password."""
    email = "wrongpass@example.com"
    _register_and_get_token(client, email, "correctpass", "User")

    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_with_unknown_email(client: TestClient) -> None:
    """Login fails for an unregistered email."""
    resp = client.post("/api/auth/login", json={
        "email": "ghost@example.com",
        "password": "whatever",
    })
    assert resp.status_code == 401


def test_me_idempotent_across_calls(client: TestClient) -> None:
    """Calling /me twice returns the same user."""
    email = "grace@example.com"
    name = "Grace Hopper"

    token = _register_and_get_token(client, email, "hopperpass", name)

    first = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    second = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["email"] == email


def test_update_me_onboarding(client: TestClient) -> None:
    """PATCH /me updates onboarding_completed."""
    token = _register_and_get_token(client, "update@example.com", "updateme", "Update Me")

    resp = client.patch(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"onboarding_completed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["onboarding_completed"] is True


def test_register_preflight_allows_railway_origin(client: TestClient) -> None:
    """Railway-hosted web deployments should pass CORS preflight for auth."""
    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://openhuman-web.up.railway.app"],
        allow_origin_regex=r"https://.*\.up\.railway\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.include_router(auth_router)
    test_app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]

    with TestClient(test_app) as cors_client:
        response = cors_client.options(
            "/api/auth/register",
            headers={
                "Origin": "https://openhuman-web.up.railway.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://openhuman-web.up.railway.app"
    )
