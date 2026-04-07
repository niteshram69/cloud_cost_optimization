"""Pydantic schemas for cost analysis requests and responses."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CostRecordResponse(BaseModel):
    """Response with cost record details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    resource_id: str
    provider: str
    service_type: str
    region: str | None
    cost_amount: Decimal
    currency: str
    usage_quantity: Decimal
    usage_unit: str
    period_start: datetime
    period_end: datetime
    description: str | None
    created_at: datetime


class CostSummaryResponse(BaseModel):
    """Summary of costs by various dimensions."""
    total_cost: Decimal
    currency: str
    period_start: datetime
    period_end: datetime
    by_provider: dict[str, Decimal]
    by_service: dict[str, Decimal]
    by_region: dict[str, Decimal]
    record_count: int


class BenchmarkResponse(BaseModel):
    """Response with benchmark details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    description: str | None
    service_type: str
    provider: str
    region: str | None
    avg_cost_per_unit: Decimal | None
    min_cost_per_unit: Decimal | None
    max_cost_per_unit: Decimal | None
    unit: str
    source: str | None
    valid_from: datetime
    valid_until: datetime | None


class BenchmarkCreateRequest(BaseModel):
    """Request to create a benchmark."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    service_type: str
    provider: str
    region: str | None = None
    avg_cost_per_unit: Decimal | None = None
    min_cost_per_unit: Decimal | None = None
    max_cost_per_unit: Decimal | None = None
    unit: str
    source: str | None = None
    valid_from: datetime
    valid_until: datetime | None = None


class CostComparisonRequest(BaseModel):
    """Request to compare costs against benchmarks."""
    resource_id: str | None = None  # Compare specific resource
    service_type: str | None = None  # Or all of a service type
    period_months: int = Field(default=1, ge=1, le=12)


class CostComparisonResult(BaseModel):
    """Result of cost comparison."""
    resource_id: str
    service_type: str
    provider: str
    current_cost: Decimal
    current_unit_cost: Decimal
    unit: str
    benchmark_avg: Decimal | None
    benchmark_min: Decimal | None
    benchmark_max: Decimal | None
    variance_pct: Decimal | None  # How much above/below benchmark
    potential_savings: Decimal | None
    comparison_status: str  # 'optimal', 'above_average', 'high', 'no_benchmark'


class CostAnomaly(BaseModel):
    """Detected cost anomaly."""
    resource_id: str
    service_type: str
    detected_at: datetime
    expected_cost: Decimal
    actual_cost: Decimal
    variance_pct: Decimal
    severity: str  # 'low', 'medium', 'high'


class CostTrendResponse(BaseModel):
    """Cost trend over time."""
    period: str  # 'daily', 'weekly', 'monthly'
    data_points: list[dict]  # {date, total_cost, by_provider, by_service}
