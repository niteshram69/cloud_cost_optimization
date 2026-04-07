"""Cost module database models."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CloudProvider
from app.core.database import Base


class CostRecord(Base):
    """Individual cost records from billing data."""
    
    __tablename__ = "cost_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # References
    ingestion_job_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metadata_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("metadata_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Resource identification
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(20),
        default=CloudProvider.OTHER.value,
        nullable=False,
        index=True,
    )
    service_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 'EC2', 'S3', 'BigQuery', 'Blob Storage', etc.
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Cost details
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    usage_quantity: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    usage_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'GB-Month', 'Hours', 'Requests', etc.
    # Time period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Raw billing data reference
    billing_line_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[dict | None] = mapped_column(Text, nullable=True)  # JSON
    # Additional context
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    # Relationships
    ingestion_job: Mapped["IngestionJob"] = relationship("IngestionJob", back_populates="cost_records")
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision",
        back_populates="cost_record",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Benchmark(Base):
    """Cost benchmarks for comparison."""
    
    __tablename__ = "benchmarks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )  # NULL for global benchmarks
    # Benchmark definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Benchmark values
    avg_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 6), nullable=True)
    min_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 6), nullable=True)
    max_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    # Data source
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 'industry_report', 'historical_data', 'provider_pricing'
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
