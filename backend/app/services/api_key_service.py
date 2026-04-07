import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import APIKey, User


class APIKeyService:
    def __init__(self, db: Session):
        self.db = db

    def create_key(self, user: User, name: str, scopes: list[str]) -> tuple[APIKey, str]:
        raw_key = f"ctk_live_{secrets.token_urlsafe(32)}"
        key_prefix = raw_key[:20]
        key_hash = self._hash_key(raw_key)

        item = APIKey(
            user_id=user.id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=",".join(sorted(set(scopes))),
            is_active=True,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item, raw_key

    def list_user_keys(self, user_id: int) -> list[APIKey]:
        return self.db.scalars(
            select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        ).all()

    def revoke_key(self, user_id: int, api_key_id: int) -> APIKey:
        key = self.db.scalar(select(APIKey).where(APIKey.id == api_key_id, APIKey.user_id == user_id))
        if not key:
            raise ValueError("API key not found")
        key.is_active = False
        key.revoked_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(key)
        return key

    def authenticate_key(self, raw_key: str) -> tuple[APIKey, User]:
        key_prefix = raw_key[:20]
        key_hash = self._hash_key(raw_key)
        key = self.db.scalar(
            select(APIKey).where(
                APIKey.key_prefix == key_prefix,
                APIKey.key_hash == key_hash,
                APIKey.is_active.is_(True),
            )
        )
        if not key:
            raise ValueError("Invalid API key")

        user = self.db.scalar(select(User).where(User.id == key.user_id, User.is_active.is_(True)))
        if not user:
            raise ValueError("API key user is inactive")

        key.last_used_at = datetime.now(UTC)
        self.db.commit()
        return key, user

    def _hash_key(self, raw_key: str) -> str:
        return hmac.new(
            settings.api_key_secret.encode("utf-8"),
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
