from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DataTemperature


class StoragePricingRecord(Base):
    __tablename__ = "storage_pricing_records"
    __table_args__ = (
        UniqueConstraint(
            "cloud",
            "native_tier",
            "region",
            "currency",
            "pricing_version",
            name="uq_storage_pricing_version",
        ),
        Index(
            "ix_storage_pricing_lookup",
            "canonical_tier",
            "pricing_version",
            "currency",
            "region",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cloud: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False, default="storage")
    canonical_tier: Mapped[DataTemperature] = mapped_column(Enum(DataTemperature), nullable=False, index=True)
    native_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    storage_price_per_gb: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_price_per_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    pricing_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    source_offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
