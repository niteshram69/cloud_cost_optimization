"""Authentication API routes."""

from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import CurrentUserDependency, get_current_user
from app.modules.auth.schemas import (
    APIKeyCreateRequest,
    APIKeyListResponse,
    APIKeyResponse,
    PasswordChangeRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])

# Rate limiter for auth endpoints
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    service = AuthService(db)
    user = await service.register(data)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and get access/refresh tokens."""
    service = AuthService(db)
    user = await service.authenticate(data.email, data.password)
    return await service.create_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    service = AuthService(db)
    return await service.refresh_tokens(data.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user information."""
    service = AuthService(db)
    user = await service.user_repo.get_by_id(int(current_user["id"]))
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user password."""
    service = AuthService(db)
    await service.change_password(
        int(current_user["id"]),
        data.current_password,
        data.new_password,
    )


# API Key management endpoints
@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: APIKeyCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key for machine-to-machine authentication."""
    service = AuthService(db)
    api_key, plain_key = await service.create_api_key(int(current_user["id"]), data)
    
    # Build response with full key (only shown once)
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=plain_key,
        key_prefix=plain_key[:12] + "...",
        user_id=api_key.user_id,
        scopes=api_key.scopes,
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=list[APIKeyListResponse])
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for current user (without full key)."""
    service = AuthService(db)
    keys = await service.list_api_keys(int(current_user["id"]))
    
    return [
        APIKeyListResponse(
            id=k.id,
            name=k.name,
            key_prefix="cintel_..." + k.key_hash[-8:] if k.key_hash else "unknown",
            scopes=k.scopes,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API key."""
    service = AuthService(db)
    await service.revoke_api_key(int(current_user["id"]), key_id)
