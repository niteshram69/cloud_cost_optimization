from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CircuitBreakerAction, CircuitBreakerOutcome


class CircuitBreakerEvent(Base):
    __tablename__ = "circuit_breaker_events"
    __table_args__ = (
        Index("idx_circuit_breaker_active_backoff", "resource_record_id", "backoff_until"),
        Index("idx_circuit_breaker_occurred", "occurred_at"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_record_id: Mapped[int] = mapped_column(
        ForeignKey("storage_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    migration_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("migration_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action_attempted: Mapped[CircuitBreakerAction] = mapped_column(Enum(CircuitBreakerAction), nullable=False)
    outcome: Mapped[CircuitBreakerOutcome] = mapped_column(Enum(CircuitBreakerOutcome), nullable=False)

    failure_code: Mapped[str] = mapped_column(String(80), nullable=False)
    failure_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    backoff_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resource = relationship("StorageRecord")
    user = relationship("User")
    migration_plan = relationship("MigrationPlan")
