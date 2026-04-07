from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DataTemperature


class CanonicalTierMapping(Base):
    __tablename__ = "canonical_tier_mappings"
    __table_args__ = (
        UniqueConstraint("cloud", "native_tier", name="uq_canonical_tier_mapping"),
        Index("ix_canonical_tier_lookup", "cloud", "native_tier", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cloud: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    native_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_tier: Mapped[DataTemperature] = mapped_column(Enum(DataTemperature), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
