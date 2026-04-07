"""FastAPI dependencies for database, Redis, and authentication."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.redis import get_redis
from app.core.security import decode_token
from app.modules.auth.service import AuthService

security = HTTPBearer(auto_error=False)


def _decode_access_token(token: str) -> dict:
    """Decode an access token and return basic user claims."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    return {"id": user_id, "email": payload.get("email"), "auth_type": "jwt"}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Validate JWT token and return current user data (JWT required)."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return _decode_access_token(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Verify user is active (placeholder for future user status checks)."""
    # TODO: Check if user is active in database
    return current_user


async def get_jwt_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """Return JWT user if present and valid, otherwise None."""
    if not credentials:
        return None

    try:
        return _decode_access_token(credentials.credentials)
    except AuthenticationError:
        return None


async def get_api_key_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    """Validate API key from request header and return user data."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None

    service = AuthService(db)
    key_record = await service.validate_api_key(api_key)
    if not key_record:
        return None

    user = await service.user_repo.get_by_id(key_record.user_id)
    if not user or not user.is_active:
        return None

    return {"id": str(user.id), "email": user.email, "auth_type": "api_key"}


async def get_current_user_or_api_key(
    jwt_user: dict | None = Depends(get_jwt_user_optional),
    api_key_user: dict | None = Depends(get_api_key_user),
) -> dict:
    """Authenticate via JWT or API key."""
    user = jwt_user or api_key_user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


# Common dependencies
DBDependency = Depends(get_db)
RedisDependency = Depends(get_redis)
CurrentUserDependency = Depends(get_current_user_or_api_key)
