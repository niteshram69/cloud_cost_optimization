from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr


class ResourceIngestItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    resource_id: StrictStr = Field(min_length=1, max_length=255)
    provider: Literal["AWS", "GCP", "AZURE"]
    region: StrictStr = Field(min_length=1, max_length=80)
    current_storage_tier: StrictStr = Field(min_length=1, max_length=120)
    intent_tier: StrictStr | None = Field(default=None, max_length=120)

    object_size_bytes: StrictInt = Field(ge=0)
    object_age_days: StrictInt = Field(ge=0)
    last_access_days: StrictInt = Field(ge=0)
    requests_30d: StrictInt = Field(ge=0)
    requests_90d: StrictInt = Field(ge=0)
    read_write_ratio: StrictFloat = Field(ge=0)
    access_std_dev: StrictFloat = Field(ge=0)
    estimated_monthly_cost_usd: StrictFloat = Field(ge=0)
    storage_cost_per_gb: StrictFloat | None = Field(default=None, ge=0)
    retrieval_cost_per_gb: StrictFloat | None = Field(default=None, ge=0)

    billing_realism: Literal["ESTIMATE", "EXPORT", "LIVE"] = "ESTIMATE"
    integration_permission: Literal["READ_ONLY", "READ_WRITE", "NONE"] = "READ_ONLY"


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Keep batch ingestion resilient: each item is validated inside the service so one bad
    # record does not fail the whole request payload.
    resources: list[Any] = Field(min_length=1, max_length=10000)


class OptimizerDecisionSchema(BaseModel):
    classification: Literal["HOT", "WARM", "COLD", "ARCHIVE", "DEEP_ARCHIVE"]
    action: Literal["MOVE_TO_PREDICTED_TIER", "MOVE_TO_STANDARD_IA", "RETAIN"]
    decision_state: Literal["PREDICTED", "FALLBACK", "NO_OP", "BLOCKED"]
    recommended_provider: Literal["AWS", "GCP", "AZURE"]
    recommended_storage_tier: str
    observed_tier: str
    intent_tier: str | None
    observed_temperature: str
    access_frequency: float
    recency_score: float
    effective_access: float
    access_recency_score: float
    temperature_score: float
    estimated_savings: float
    confidence_final: float
    model_confidence: float
    migration_risk: float
    execution_eligibility: Literal["EXECUTABLE", "DRY_RUN_ONLY"]
    confidence_trace: dict[str, float | str]
    rule_trace: list[str]
    technical_trace: dict[str, float | int | str]


class IngestItemSuccess(BaseModel):
    index: int
    resource_id: str
    status: Literal["SUCCESS"] = "SUCCESS"
    resource_pk: int
    recommendation_pk: int
    decision: OptimizerDecisionSchema


class IngestItemError(BaseModel):
    index: int
    resource_id: str | None = None
    status: Literal["ERROR"] = "ERROR"
    error_code: str
    reason: str


class IngestResponse(BaseModel):
    ingestion_started_at: datetime
    ingestion_completed_at: datetime
    total_received: int
    total_succeeded: int
    total_failed: int
    succeeded: list[IngestItemSuccess]
    failed: list[IngestItemError]
