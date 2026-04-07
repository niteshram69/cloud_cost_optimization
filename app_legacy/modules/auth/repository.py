"""Database access layer for user and API key operations."""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import APIKey, User


class UserRepository:
    """Repository for user database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    async def create(self, user: User) -> User:
        """Create a new user."""
        user.created_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user
    
    async def update(self, user: User) -> User:
        """Update existing user."""
        await self.db.flush()
        await self.db.refresh(user)
        return user


class APIKeyRepository:
    """Repository for API key database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, key_id: int, user_id: int) -> APIKey | None:
        """Get API key by ID and user ID."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_hash(self, key_hash: str) -> APIKey | None:
        """Get API key by its hash."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[APIKey]:
        """List all active API keys."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.is_active.is_(True))
        )
        return list(result.scalars().all())
    
    async def list_by_user(self, user_id: int) -> list[APIKey]:
        """List all API keys for a user."""
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def create(self, api_key: APIKey) -> APIKey:
        """Create a new API key."""
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key
    
    async def delete(self, api_key: APIKey) -> None:
        """Delete an API key."""
        await self.db.delete(api_key)
        await self.db.flush()
    
    async def update_last_used(self, api_key: APIKey) -> None:
        """Update last used timestamp."""
        from datetime import datetime, timezone
        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
