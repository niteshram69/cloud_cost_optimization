from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas.migration_authorization import MigrationAuthorizeRequest, MigrationAuthorizeResponse
from backend.app.services.migration_authorization_service import MigrationAuthorizationService

router = APIRouter(tags=["migrations"])


@router.post("/migrations/authorize", response_model=MigrationAuthorizeResponse)
def authorize_migration(
    payload: MigrationAuthorizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MigrationAuthorizeResponse:
    service = MigrationAuthorizationService(db)
    return service.authorize_and_execute(current_user=current_user, payload=payload)
