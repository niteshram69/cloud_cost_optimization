from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider


class BucketObjectReference(Base):
    __tablename__ = "bucket_object_references"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bucket_id",
            "cloud_provider",
            "region",
            "storage_class",
            "resource_name",
            name="uq_bucket_object_ref",
        ),
        Index(
            "ix_bucket_object_lookup",
            "user_id",
            "bucket_id",
            "cloud_provider",
            "region",
            "storage_class",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    storage_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    bucket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cloud_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    storage_class: Mapped[str] = mapped_column(String(120), nullable=False, default="STANDARD")
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    size_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    requests_30d: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    feature_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
