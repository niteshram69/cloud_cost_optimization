from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.models.enums import CloudProvider


class PricingIngestionRun(Base):
    __tablename__ = "pricing_ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cloud: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    provider_feed: Mapped[str] = mapped_column(String(120), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
