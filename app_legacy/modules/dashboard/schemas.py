"""Pydantic schemas for dashboard data aggregation."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    """High-level dashboard summary."""
    total_monthly_cost: Decimal
    cost_change_pct: float  # vs previous period
    total_resources: int
    classification_summary: dict[str, int]  # category -> count
    pending_decisions: int
    potential_savings: Decimal
    active_providers: list[str]


class CostOverviewChart(BaseModel):
    """Cost data formatted for chart visualization."""
    labels: list[str]  # Period labels
    datasets: list[dict]  # Chart.js format: {label, data, color}


class ResourceBreakdownChart(BaseModel):
    """Resource breakdown for pie/donut charts."""
    by_type: list[dict]  # [{type, count, percentage}]
    by_provider: list[dict]  # [{provider, count, cost}]
    by_region: list[dict]  # [{region, count, cost}]


class TopResourcesTable(BaseModel):
    """Top resources by cost for table display."""
    resource_id: str
    service_type: str
    provider: str
    monthly_cost: Decimal
    trend: str  # 'up', 'down', 'stable'
    trend_pct: float


class RecommendationsWidget(BaseModel):
    """Quick recommendations for dashboard widget."""
    total_recommendations: int
    by_priority: list[dict]  # [{priority, count, potential_savings}]
    top_actions: list[dict]  # [{action, resource_id, savings}]


class IngestionStatusWidget(BaseModel):
    """Recent ingestion job status."""
    recent_jobs: list[dict]  # [{id, status, file_name, records_processed}]
    jobs_today: int
    jobs_this_week: int
    total_records: int


class TimeSeriesRequest(BaseModel):
    """Request for time-series data."""
    start_date: datetime
    end_date: datetime
    granularity: str = "daily"  # 'hourly', 'daily', 'weekly', 'monthly'
    group_by: str | None = None  # 'provider', 'service', 'region'


class AlertItem(BaseModel):
    """Dashboard alert/warning item."""
    severity: str  # 'info', 'warning', 'critical'
    message: str
    resource_id: str | None
    action_url: str | None
    detected_at: datetime


class DashboardAlertsResponse(BaseModel):
    """Active alerts for the dashboard."""
    alerts: list[AlertItem]
    total_count: int
    critical_count: int
    warning_count: int
