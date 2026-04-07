"""Pydantic schemas for decision and webhook operations."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DecisionResponse(BaseModel):
    """Response with decision details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    cost_record_id: int | None
    recommendation: str
    action_type: str
    confidence: float
    estimated_savings_monthly: Decimal | None
    estimated_cost_to_implement: Decimal | None
    currency: str
    is_automated: bool
    approved_at: datetime | None
    executed_at: datetime | None
    webhook_status: str
    webhook_attempts: int
    created_at: datetime


class DecisionCreateRequest(BaseModel):
    """Request to create a decision (typically auto-generated)."""
    cost_record_id: int | None = None
    recommendation: str
    action_type: str = Field(pattern="^(archive|delete|downsize|rightsize|migrate|review|none)$")
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_savings_monthly: Decimal | None = None
    estimated_cost_to_implement: Decimal | None = None
    is_automated: bool = False
    webhook_url: HttpUrl | None = None


class DecisionApproveRequest(BaseModel):
    """Request to approve and execute a decision."""
    webhook_url: HttpUrl | None = None


class DecisionDismissRequest(BaseModel):
    """Request to dismiss a decision."""
    reason: str


class WebhookDeliveryRequest(BaseModel):
    """Request to trigger webhook delivery for a decision."""
    pass


class WebhookLogResponse(BaseModel):
    """Response with webhook delivery log."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    attempt_number: int
    status: str
    status_code: int | None
    error_message: str | None
    triggered_at: datetime
    duration_ms: int | None


class DecisionStatsResponse(BaseModel):
    """Statistics for decisions."""
    total_decisions: int
    by_status: dict[str, int]
    by_action_type: dict[str, int]
    pending_approval: int
    total_estimated_savings: Decimal
    automated_executions: int
    webhook_deliveries: int
