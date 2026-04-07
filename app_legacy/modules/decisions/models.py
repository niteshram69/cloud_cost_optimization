"""Decisions module database models."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DecisionAction, WebhookStatus
from app.core.database import Base


class Decision(Base):
    """Automated or manual decisions/recommendations."""
    
    __tablename__ = "decisions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # References
    cost_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("cost_records.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Decision details
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-readable recommendation text
    action_type: Mapped[str] = mapped_column(
        String(20),
        default=DecisionAction.REVIEW.value,
        nullable=False,
        index=True,
    )
    # 'archive', 'delete', 'downsize', 'rightsize', 'migrate', 'review', 'none'
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 0.0 to 1.0
    # Cost impact estimate
    estimated_savings_monthly: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    estimated_cost_to_implement: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # Decision logic
    rule_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Identifier for the rule that generated this decision
    rule_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Human-readable explanation of why this decision was made
    # Execution status
    is_automated: Mapped[bool] = mapped_column(default=False, nullable=False)
    # If true, action will be executed automatically
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Success/failure message
    # Webhook for notifications
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_status: Mapped[str] = mapped_column(
        String(20),
        default=WebhookStatus.PENDING.value,
        nullable=False,
    )
    webhook_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    webhook_last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Additional context
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {original_config, suggested_config, risk_level, affected_resources}
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dismiss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    # Relationships
    cost_record: Mapped["CostRecord"] = relationship("CostRecord", back_populates="decisions")
    webhook_logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="decision",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WebhookLog(Base):
    """Log of webhook delivery attempts."""
    
    __tablename__ = "webhook_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # 'success', 'failure'
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON string of the payload sent
    triggered_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Relationships
    decision: Mapped["Decision"] = relationship("Decision", back_populates="webhook_logs")
