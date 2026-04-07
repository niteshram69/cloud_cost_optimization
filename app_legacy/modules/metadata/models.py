"""Metadata module database models."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MetadataRecord(Base):
    """Extracted metadata from ingested data."""
    
    __tablename__ = "metadata_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ingestion_job_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Entity identification
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 'storage_bucket', 'compute_instance', 'database', 'log_file', 'billing_entry'
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Provider identification
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 'aws', 'gcp', 'azure', 'on_premise'
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Technical attributes
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Varies by entity_type:
    # storage_bucket: {size_gb, object_count, storage_class, versioning_enabled}
    # compute_instance: {instance_type, vcpus, memory_gb, running_hours}
    # database: {engine, instance_class, storage_allocated, connections}
    # billing_entry: {service_name, usage_type, usage_quantity, unit}
    # Extracted tags/labels
    tags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {environment: 'prod', team: 'platform', project: 'analytics'}
    # Temporal metadata
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resource_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resource_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Raw source reference
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Original row/data
    
    # Relationships
    ingestion_job: Mapped["IngestionJob"] = relationship("IngestionJob", back_populates="metadata_records")
    classification_results: Mapped[list["ClassificationResult"]] = relationship(
        "ClassificationResult",
        back_populates="metadata_record",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
