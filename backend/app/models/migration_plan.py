from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, BigInteger, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, MigrationExecutionMode, MigrationLifecycleState


class MigrationPlan(Base):
    __tablename__ = "migration_plans"
    __table_args__ = (
        Index("idx_migration_plan_user_state", "user_id", "state"),
        Index("idx_migration_plan_resource", "resource_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_record_id: Mapped[int] = mapped_column(
        ForeignKey("storage_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    source_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    target_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    approved_target_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    ml_predicted_tier: Mapped[str] = mapped_column(String(120), nullable=False)

    confidence_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    guardrail_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution_mode: Mapped[MigrationExecutionMode] = mapped_column(
        Enum(MigrationExecutionMode),
        nullable=False,
        default=MigrationExecutionMode.MANUAL,
    )
    authorized_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    state: Mapped[MigrationLifecycleState] = mapped_column(
        Enum(MigrationLifecycleState),
        nullable=False,
        default=MigrationLifecycleState.PLANNED,
        index=True,
    )

    override_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risks_acknowledged: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dry_run_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    monitoring_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    authorizer = relationship("User", foreign_keys=[authorized_by])
    recommendation = relationship("Recommendation")
    resource = relationship("StorageRecord")
