"""Business logic for authentication and user management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.modules.auth.models import APIKey, User
from app.modules.auth.repository import APIKeyRepository, UserRepository
from app.modules.auth.schemas import (
    APIKeyCreateRequest,
    TokenResponse,
    UserRegisterRequest,
)


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.api_key_repo = APIKeyRepository(db)
    
    async def register(self, data: UserRegisterRequest) -> User:
        """Register a new user."""
        # Check if email already exists
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise DuplicateResourceError("User", "email", data.email)
        
        # Create new user
        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            organization_id=data.organization_id,
        )
        return await self.user_repo.create(user)
    
    async def authenticate(self, email: str, password: str) -> User:
        """Authenticate user with email and password."""
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise AuthenticationError("Invalid credentials")
        
        if not user.is_active:
            raise AuthenticationError("Account is disabled")
        
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")
        
        return user
    
    async def create_tokens(self, user: User) -> TokenResponse:
        """Create access and refresh tokens for user."""
        token_data = {"sub": str(user.id), "email": user.email}
        
        return TokenResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
            token_type="bearer",
            expires_in=1800,  # 30 minutes
        )
    
    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token."""
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")
            
            user_id = int(payload.get("sub"))
            user = await self.user_repo.get_by_id(user_id)
            
            if not user or not user.is_active:
                raise AuthenticationError("User not found or inactive")
            
            return await self.create_tokens(user)
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {str(e)}")
    
    async def change_password(self, user_id: int, current: str, new: str) -> None:
        """Change user password."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User", str(user_id))
        
        if not verify_password(current, user.password_hash):
            raise ValidationError("Current password is incorrect")
        
        user.password_hash = hash_password(new)
        await self.user_repo.update(user)
    
    async def create_api_key(self, user_id: int, data: APIKeyCreateRequest) -> tuple[APIKey, str]:
        """Create new API key for user. Returns (APIKey object, plain key)."""
        # Generate key and hash
        plain_key = generate_api_key()
        key_hash = hash_password(plain_key)  # Use same hashing for consistency
        
        api_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            name=data.name,
            expires_at=data.expires_at,
            scopes=data.scopes,
        )
        
        created = await self.api_key_repo.create(api_key)
        return created, plain_key
    
    async def list_api_keys(self, user_id: int) -> list[APIKey]:
        """List all API keys for user."""
        return await self.api_key_repo.list_by_user(user_id)
    
    async def revoke_api_key(self, user_id: int, key_id: int) -> None:
        """Revoke (delete) an API key."""
        api_key = await self.api_key_repo.get_by_id(key_id, user_id)
        if not api_key:
            raise ResourceNotFoundError("API Key", str(key_id))
        
        await self.api_key_repo.delete(api_key)
    
    async def validate_api_key(self, plain_key: str) -> APIKey | None:
        """Validate an API key and update last used timestamp."""
        if not plain_key.startswith(settings.API_KEY_PREFIX):
            return None

        # API keys are bcrypt-hashed (salted), so deterministic DB lookup is not possible.
        # Validate by checking each active hash with passlib's verify.
        active_keys = await self.api_key_repo.list_active()

        for api_key in active_keys:
            try:
                if not verify_password(plain_key, api_key.key_hash):
                    continue
            except ValueError:
                # Skip malformed hashes instead of failing authentication globally.
                continue

            if api_key.is_expired:
                return None

            await self.api_key_repo.update_last_used(api_key)
            return api_key

        return None
