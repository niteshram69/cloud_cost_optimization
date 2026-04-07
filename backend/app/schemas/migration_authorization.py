from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator


RiskCodeLiteral = Literal["LATENCY", "RETRIEVAL_COST", "MANUAL_OVERRIDE"]
OverrideTypeLiteral = Literal["USER_CONFIRMED"]


class MigrationAuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recommendation_id: StrictInt | None = Field(default=None, gt=0)
    resource_id: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    approved_target_tier: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    override_type: OverrideTypeLiteral | None = None
    justification: StrictStr | None = Field(default=None, min_length=3, max_length=500)
    override_confidence: StrictBool = False
    acknowledged_risks: list[RiskCodeLiteral] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_identifiers(self) -> "MigrationAuthorizeRequest":
        if self.recommendation_id is None and not self.resource_id:
            raise ValueError("Either recommendation_id or resource_id must be provided.")
        return self


class MigrationAuthorizeResponse(BaseModel):
    migration_plan_id: int
    recommendation_id: int
    resource_id: str
    migration_state: str
    execution_result: Literal["COMPLETED", "ROLLED_BACK", "BLOCKED", "SIMULATED_RESULTS"]
    execution_eligibility: Literal["NONE", "DRY_RUN_ELIGIBLE", "EXECUTABLE"]
    message: str
    confidence_final: float
    guardrail_trace: list[str] = Field(default_factory=list)
    dry_run_report: dict[str, Any] = Field(default_factory=dict)
    monitoring_report: dict[str, Any] | None = None
    audit_event_id: int | None = None
    authorized_at: datetime
