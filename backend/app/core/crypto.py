import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.app.core.config import settings


def _fernet() -> Fernet:
    secret = settings.integration_credentials_secret or settings.jwt_secret_key
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_credentials(payload: dict[str, Any]) -> str:
    token = _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_credentials(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
