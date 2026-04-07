"""Dashboard API routes for aggregated data."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import CurrentUserDependency
from app.modules.dashboard.schemas import (
    CostOverviewChart,
    DashboardAlertsResponse,
    DashboardSummaryResponse,
    IngestionStatusWidget,
    RecommendationsWidget,
    ResourceBreakdownChart,
    TopResourcesTable,
)
from app.modules.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_summary(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get high-level dashboard summary."""
    service = DashboardService(db)
    summary = await service.get_summary(int(current_user["id"]))
    return summary


@router.get("/cost-chart", response_model=CostOverviewChart)
async def get_cost_chart(
    months: int = 6,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get cost data formatted for chart visualization."""
    service = DashboardService(db)
    chart = await service.get_cost_chart(int(current_user["id"]), months)
    return chart


@router.get("/resource-breakdown", response_model=ResourceBreakdownChart)
async def get_resource_breakdown(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get resource breakdown for visualization."""
    service = DashboardService(db)
    breakdown = await service.get_resource_breakdown(int(current_user["id"]))
    return breakdown


@router.get("/top-resources", response_model=list[TopResourcesTable])
async def get_top_resources(
    limit: int = 10,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get top resources by cost."""
    service = DashboardService(db)
    resources = await service.get_top_resources(int(current_user["id"]), limit)
    return resources


@router.get("/recommendations", response_model=RecommendationsWidget)
async def get_recommendations(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get recommendations summary for dashboard."""
    service = DashboardService(db)
    recs = await service.get_recommendations_widget(int(current_user["id"]))
    return recs


@router.get("/ingestion-status", response_model=IngestionStatusWidget)
async def get_ingestion_status(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get recent ingestion job status."""
    service = DashboardService(db)
    status = await service.get_ingestion_status(int(current_user["id"]))
    return status


@router.get("/alerts", response_model=DashboardAlertsResponse)
async def get_alerts(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get active alerts for the dashboard."""
    service = DashboardService(db)
    alerts = await service.get_alerts(int(current_user["id"]))
    return alerts
