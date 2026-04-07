"""Dashboard response schemas for admin and client views."""

from __future__ import annotations

from pydantic import BaseModel


class ProviderSpendItem(BaseModel):
    provider: str
    monthly_cost: float


class RegionComparisonItem(BaseModel):
    region: str
    before_cost: float
    after_cost: float


class AdminDashboardResponse(BaseModel):
    currency: str
    total_cloud_spend: float
    optimized_spend: float
    savings_achieved: float
    migration_status: dict[str, int]
    error_rate: float
    api_usage: dict[str, int]
    ml_confidence_avg: float
    classification_drift: float
    objects_per_class: dict[str, int]
    provider_spend: list[ProviderSpendItem]


class ClientDashboardResponse(BaseModel):
    tenant_id: str
    currency: str
    objects_analyzed: int
    monthly_cost_before: float
    monthly_cost_after: float
    monthly_savings: float
    yearly_savings: float
    region_comparison: list[RegionComparisonItem]
    class_distribution: dict[str, int]
