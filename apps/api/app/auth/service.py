import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UpdateUserRequest
from app.core.config import settings
from app.organizations.schemas import CreateOrganizationRequest
from app.organizations.service import create_org

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def register_user(db: AsyncSession, email: str, password: str, name: str) -> str:
    """Create a new user and return a JWT access token."""
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=email,
        name=name,
        password_hash=_hash_password(password),
        onboarding_completed=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    try:
        await create_org(
            db,
            user.id,
            CreateOrganizationRequest(name="My Organization"),
        )
    except Exception:
        logger.exception("Failed to create default org for user %s", user.id)

    return _create_access_token(str(user.id))


async def login_user(db: AsyncSession, email: str, password: str) -> str:
    """Verify credentials and return a JWT access token."""
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.password_hash or not _verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is disabled")

    return _create_access_token(str(user.id))


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    return await db.scalar(select(User).where(User.id == user_id))


async def delete_user(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.commit()


async def update_user(db: AsyncSession, user: User, data: UpdateUserRequest) -> User:
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        existing = await db.scalar(
            select(User).where(User.email == data.email, User.id != user.id)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )
        user.email = data.email
    if data.current_password is not None and data.new_password is not None:
        if not user.password_hash or not _verify_password(data.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        user.password_hash = _hash_password(data.new_password)
    elif data.current_password is not None or data.new_password is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both current_password and new_password are required to change password",
        )
    if data.onboarding_completed is not None:
        user.onboarding_completed = data.onboarding_completed
    await db.commit()
    await db.refresh(user)
    return user
