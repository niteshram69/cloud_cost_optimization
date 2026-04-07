from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Index, Integer, BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider


class MetricHistory(Base):
    __tablename__ = "metric_history"
    __table_args__ = (
        UniqueConstraint("resource_record_id", "snapshot_date", name="uq_metric_history_resource_date"),
        Index("idx_metric_history_resource_window", "resource_record_id", "snapshot_date"),
        Index("idx_metric_history_snapshot_provider", "snapshot_date", "provider"),
    )

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_record_id: Mapped[int] = mapped_column(
        ForeignKey("storage_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    requests_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tier_class: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_telemetry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    resource = relationship("StorageRecord")
