from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider


class FinOpsResource(Base):
    __tablename__ = "finops_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(80), nullable=False, default="global")
    intent_tier: Mapped[str | None] = mapped_column(String(120), nullable=True)

    object_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    object_age_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_access_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requests_90d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    read_write_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    access_std_dev: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    storage_cost_per_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retrieval_cost_per_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    size_mb: Mapped[float] = mapped_column(Float, nullable=False)
    requests_30d: Mapped[int] = mapped_column(Integer, nullable=False)
    days_observed: Mapped[int] = mapped_column(Integer, nullable=False)
    has_real_billing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_storage_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    billing_realism: Mapped[str] = mapped_column(String(20), nullable=False, default="ESTIMATE")
    integration_permission: Mapped[str] = mapped_column(String(20), nullable=False, default="READ_ONLY")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    recommendations = relationship("FinOpsRecommendation", back_populates="resource")
