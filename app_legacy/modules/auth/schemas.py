"""Pydantic schemas for authentication requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Base schemas
class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr
    full_name: str | None = None


class APIKeyBase(BaseModel):
    """Base API key schema."""
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: datetime | None = None
    scopes: str = "read,write"


# Request schemas
class UserRegisterRequest(UserBase):
    """Request schema for user registration."""
    password: str = Field(..., min_length=8, max_length=100)
    organization_id: str | None = None


class UserLoginRequest(BaseModel):
    """Request schema for user login."""
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    """Request schema for token refresh."""
    refresh_token: str


class APIKeyCreateRequest(APIKeyBase):
    """Request schema for creating API key."""
    pass


# Response schemas
class TokenResponse(BaseModel):
    """Response schema for authentication tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds


class UserResponse(UserBase):
    """Response schema for user data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_active: bool
    email_verified: bool
    organization_id: str | None = None
    created_at: datetime
    updated_at: datetime


class APIKeyResponse(APIKeyBase):
    """Response schema for API key data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    key: str | None = None  # Only shown on creation
    key_prefix: str
    user_id: int
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class APIKeyListResponse(BaseModel):
    """Response schema for listing API keys (without full key)."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class PasswordChangeRequest(BaseModel):
    """Request schema for password change."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
