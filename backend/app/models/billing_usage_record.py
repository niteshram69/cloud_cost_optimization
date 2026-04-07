from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DataTemperature


class BillingUsageRecord(Base):
    __tablename__ = "billing_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "source_record_hash",
            name="uq_billing_usage_hash",
        ),
        Index(
            "ix_billing_usage_lookup",
            "user_id",
            "provider",
            "bucket_id",
            "usage_start",
            "usage_end",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("billing_ingestion_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    billing_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bucket_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    region: Mapped[str] = mapped_column(String(80), nullable=False, default="global", index=True)
    storage_class: Mapped[str] = mapped_column(String(120), nullable=False, default="STANDARD")
    canonical_tier: Mapped[DataTemperature] = mapped_column(Enum(DataTemperature), nullable=False, index=True)

    sku_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sku_description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    usage_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    usage_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    usage_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    usage_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="GB")
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    pricing_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source_record_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
