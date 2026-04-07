from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, BigInteger, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_event_user_time", "user_id", "timestamp"),
        Index("idx_audit_event_resource", "resource", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    migration_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("migration_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    who: Mapped[str] = mapped_column(String(128), nullable=False)
    what: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    guardrails: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risks_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_result: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    user = relationship("User")
    migration_plan = relationship("MigrationPlan")
