from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas.dashboard import (
    DataTemperatureResponse,
    GroupedRecommendationResponse,
    RecommendationResponse,
    RecommendationSummaryResponse,
    SummaryResponse,
    UserMigrationResponse,
)
from backend.app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/summary", response_model=SummaryResponse)
def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryResponse:
    service = DashboardService(db)
    return service.get_summary(user_id=current_user.id)


@router.get("/recommendations", response_model=list[RecommendationResponse])
def recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecommendationResponse]:
    service = DashboardService(db)
    return service.get_recommendations(user_id=current_user.id)


@router.get("/recommendations/grouped", response_model=list[GroupedRecommendationResponse])
def grouped_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GroupedRecommendationResponse]:
    service = DashboardService(db)
    return service.get_grouped_recommendations(user_id=current_user.id)


@router.get("/recommendations/{resource_id:path}/summary", response_model=RecommendationSummaryResponse)
def recommendation_summary(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationSummaryResponse:
    service = DashboardService(db)
    summary = service.get_recommendation_summary(user_id=current_user.id, resource_id=resource_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Recommendation summary not found.")
    return summary


@router.get("/data-temperature", response_model=DataTemperatureResponse)
def data_temperature(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DataTemperatureResponse:
    service = DashboardService(db)
    return service.get_data_temperature(user_id=current_user.id)


@router.get("/migrations", response_model=list[UserMigrationResponse])
def migrations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserMigrationResponse]:
    service = DashboardService(db)
    return service.get_user_migrations(user_id=current_user.id)
