from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decode_access_token
from backend.app.database import get_db
from backend.app.models import APIKey, Plan, User, UserAccount, UserRole
from backend.app.services.api_key_service import APIKeyService
from backend.app.services.billing_service import BillingService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@dataclass
class APIPrincipal:
    user: User
    api_key: APIKey
    account: UserAccount
    plan: Plan


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        raise credentials_error

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    return user


def require_role(*allowed_roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return current_user

    return checker


def get_api_principal(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> APIPrincipal:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
        )

    api_key_service = APIKeyService(db)
    try:
        api_key, user = api_key_service.authenticate_key(x_api_key.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    account = db.scalar(select(UserAccount).where(UserAccount.user_id == user.id))
    if not account:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account not provisioned")

    plan = db.scalar(select(Plan).where(Plan.id == account.plan_id))
    if not plan:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pricing plan not configured")

    billing = BillingService(db)
    billing.ensure_open_cycle(account=account, plan=plan)
    try:
        billing.enforce_account_access(account)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return APIPrincipal(user=user, api_key=api_key, account=account, plan=plan)
