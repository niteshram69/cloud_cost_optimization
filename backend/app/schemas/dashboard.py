from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProviderAuthorityResponse(BaseModel):
    provider: str
    ingestion_mode: str
    integration_permission: str
    mode: str
    execution_authorized: bool
    reason: str


class SummaryResponse(BaseModel):
    total_storage_cost: float
    estimated_monthly_savings: float
    hot_percentage: float
    cold_percentage: float
    archive_percentage: float
    pricing_version: str | None = None
    system_mode: str = "ANALYSIS_MODE"
    analysis_ready: bool = True
    execution_authorized: bool = False
    provider_authority: list[ProviderAuthorityResponse] = Field(default_factory=list)
    dataset_id: int | None = None
    dataset_label: str | None = None
    dataset_source: str | None = None
    dataset_source_label: str | None = None
    dataset_record_count: int | None = None
    dataset_created_at: datetime | None = None


class RecommendationResponse(BaseModel):
    id: int
    resource_name: str
    bucket_id: str | None = None
    optimization_unit: str = "OBJECT"
    current_tier: str
    current_provider: str
    recommended_tier: str
    recommended_provider: str
    estimated_monthly_savings: float
    priority: str
    status: str
    feature_snapshot: dict[str, float | int | str]
    confidence_score: float
    rule_override_trace: list[str]
    current_monthly_cost: float | None = None
    optimized_monthly_cost: float | None = None
    estimated_savings_percent: float | None = None
    pricing_version: str | None = None
    pricing_candidates: list[dict[str, float | int | str]] = Field(default_factory=list)
    cost_assumptions: dict[str, str] = Field(default_factory=dict)
    migration_advisory: dict[str, Any] | None = None
    bucket_metrics: dict[str, float | int | str | bool] | None = None
    object_references: list[str] = Field(default_factory=list)
    confidence_base_score: float | None = None
    model_confidence: float
    ml_confidence: float
    data_maturity: str
    data_maturity_score: float
    billing_realism: str
    execution_authority: str
    operational_readiness: float
    operational_readiness_band: str
    operational_readiness_reasons: list[str] = Field(default_factory=list)
    confidence_decay: dict[str, Any] | None = None
    confidence_message: str | None = None
    decision_trace: dict[str, Any] | None = None
    decision_state: str
    confidence_final: float
    confidence_trace: dict[str, Any]
    guardrail_trace: list[str] = Field(default_factory=list)
    pricing_trace: dict[str, Any]
    pricing_source: str | None = None
    pricing_confidence: str
    ingestion_mode: str
    integration_permission: str
    execution_eligibility: str
    execution_reason: str
    execution_unlock_hint: str
    recommendation_action: str = "PROPOSED"
    recommendation_state: str = "READY_FOR_DRY_RUN"
    migration_state: str
    decision_trace_block: str | None = None
    created_at: datetime


class RecommendationSummaryResponse(BaseModel):
    resource_id: str
    provider: str
    current_tier: str
    recommended_tier: str
    classification: str
    lifecycle_stage: str
    temperature_score: float
    recency_score: float
    momentum: float
    access_volatility: float
    access_frequency: float
    effective_access: float
    requests_30d: float
    requests_90d: float
    last_access_days: int | None = None
    storage_cost_current: float | None = None
    storage_cost_recommended: float | None = None
    estimated_savings: float
    migration_risk: str
    migration_risk_score: float | None = None
    confidence: float
    execution_eligibility: str
    predicted_archive_in_days: int | None = None
    reasoning: list[str] = Field(default_factory=list)


class DataTemperatureResponse(BaseModel):
    hot_count: int
    cold_count: int
    archive_count: int


class RegionUsagePoint(BaseModel):
    provider: str
    region: str
    storage_cost: float


class CloudUsageOverview(BaseModel):
    total_cost: float
    by_provider: dict[str, float]
    by_region: list[RegionUsagePoint]


class ClassificationAccuracyResponse(BaseModel):
    average_confidence: float
    high_confidence_count: int
    total_classified: int


class SystemHealthResponse(BaseModel):
    active_users: int
    running_migrations: int
    failed_migrations: int
    api_uptime_seconds: float
    pricing_version: str | None = None


class AdminMetricsResponse(BaseModel):
    cloud_usage: CloudUsageOverview
    classification_accuracy: ClassificationAccuracyResponse
    system_health: SystemHealthResponse


class AdminUserResponse(BaseModel):
    id: int
    name: str
    email: str
    company_name: str
    cloud_provider: str
    role: str
    is_active: bool
    account_state: str
    plan_code: str
    subscription_status: str | None
    current_cycle_usage: int
    included_quota: int
    overage_usage: int
    estimated_cycle_amount: float
    currency: str
    last_payment_status: str | None
    created_at: datetime


class AdminMigrationResponse(BaseModel):
    id: int
    user_id: int
    resource_name: str
    source_provider: str
    target_provider: str
    status: str
    progress_percent: float
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class UserMigrationResponse(BaseModel):
    id: int
    resource_name: str
    source_provider: str
    target_provider: str
    status: str
    progress_percent: float
    before_monthly_cost: float
    after_monthly_cost: float
    cost_delta: float
    risk_score: float
    rollback_plan: str
    migration_state: str = "PLANNED"
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class GroupedRecommendationResponse(BaseModel):
    group_key: str
    data_temperature: str
    recommended_provider: str
    recommended_tier: str
    dataset_count: int
    avg_monthly_savings: float
    total_monthly_savings: float
    avg_confidence_score: float
    risk_level: str
    pricing_version: str | None = None
    preview_resource_names: list[str] = Field(default_factory=list)
