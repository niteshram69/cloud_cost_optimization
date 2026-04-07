from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DataTemperature


class BucketAggregate(Base):
    __tablename__ = "bucket_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bucket_id",
            "cloud_provider",
            "region",
            "storage_class",
            name="uq_bucket_aggregate",
        ),
        Index(
            "ix_bucket_aggregate_lookup",
            "user_id",
            "bucket_id",
            "cloud_provider",
            "region",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    bucket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cloud_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    storage_class: Mapped[str] = mapped_column(String(120), nullable=False, default="STANDARD")

    total_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_object_size_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_requests_30d: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_requests_per_object: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    actual_monthly_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pricing_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    has_real_billing: Mapped[bool] = mapped_column(nullable=False, default=False)

    temperature: Mapped[DataTemperature] = mapped_column(Enum(DataTemperature), nullable=False, default=DataTemperature.COLD)
    classification_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observation_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    object_references: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
