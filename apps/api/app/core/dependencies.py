from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import settings
from app.core.database import get_db

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Invalid token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        token = request.query_params.get("token")
        if not token:
            raise _unauthorized("Missing bearer token")
    else:
        token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise _unauthorized("Invalid or expired token")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise _unauthorized("Token missing sub claim")

    user = await db.scalar(select(User).where(User.id == UUID(user_id)))
    if user is None or not user.is_active:
        raise _unauthorized("User not found")

    return user
