from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.app.models.enums import DataTemperature


class PricingCandidateResponse(BaseModel):
    cloud: str
    native_tier: str
    canonical_tier: str
    region: str
    storage_price_per_gb: float
    retrieval_price_per_gb: float
    monthly_cost: float
    currency: str


class PricingDecisionRequest(BaseModel):
    resource_id: str = Field(min_length=1, max_length=255)
    data_temperature: DataTemperature
    storage_gb: float = Field(gt=0)
    monthly_retrieval_gb: float = Field(ge=0)
    region_preference: str | None = Field(default=None, max_length=80)
    current_cloud: str | None = Field(default=None, max_length=16)
    current_tier: str | None = Field(default=None, max_length=120)
    current_monthly_cost: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)


class PricingDecisionResponse(BaseModel):
    resource_id: str
    data_temperature: str
    current_cloud: str | None
    current_tier: str | None
    recommended_cloud: str
    recommended_tier: str
    current_monthly_cost: float
    optimized_monthly_cost: float
    estimated_savings_percent: float
    pricing_version: str
    currency: str
    region_preference: str | None
    candidates: list[PricingCandidateResponse]
    cost_assumptions: dict[str, str]
    explanation: str


class AzurePricingSyncResponse(BaseModel):
    cloud: str
    pricing_version: str
    records_inserted: int
    records_existing: int
    source_url: str
    sync_started_at: datetime
    sync_completed_at: datetime
    status: str


class CloudPricingSyncResponse(BaseModel):
    cloud: str
    pricing_version: str
    records_inserted: int
    records_existing: int
    source_url: str
    sync_started_at: datetime
    sync_completed_at: datetime
    status: str


class PricingVersionResponse(BaseModel):
    cloud: str
    pricing_version: str
    effective_date: date
    currency: str
    records_count: int
    last_updated_at: datetime


class TopSavingsOpportunityResponse(BaseModel):
    resource_id: str
    data_temperature: str
    current_cloud: str
    current_tier: str
    recommended_cloud: str
    recommended_tier: str
    region: str
    current_monthly_cost: float
    optimized_monthly_cost: float
    monthly_savings: float
    estimated_savings_percent: float
    pricing_version: str
    currency: str


class PricingExportPayloadResponse(BaseModel):
    generated_at: datetime
    pricing_version: str
    csv_headers: list[str]
    csv_rows: list[list[str]]
    pdf_payload: dict[str, str | int | float | list[dict[str, str | int | float]]]


class TopSavingsResponse(BaseModel):
    total_considered: int
    total_monthly_savings: float
    opportunities: list[TopSavingsOpportunityResponse]
    export: PricingExportPayloadResponse
