"""Ingestion module database models."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import IngestionStatus
from app.core.database import Base


class DataSource(Base):
    """Data source configuration for recurring ingestion."""
    
    __tablename__ = "data_sources"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 's3', 'api', 'upload', 'gcs', 'azure'
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Config structure varies by type:
    # s3: {bucket, prefix, region, credentials_key}
    # api: {endpoint, method, headers, auth_type}
    # upload: {allowed_formats, max_size}
    schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Cron expression
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    # Relationships
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        "IngestionJob",
        back_populates="data_source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IngestionJob(Base):
    """Individual ingestion job tracking."""
    
    __tablename__ = "ingestion_jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=IngestionStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    # File information
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # Bytes
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256
    # Processing metadata
    job_metadata: Mapped[dict] = mapped_column(JSON, name="metadata", nullable=False, default=dict)
    # {rows_processed, columns, detected_format, errors}
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    # Relationships
    data_source: Mapped[DataSource | None] = relationship("DataSource", back_populates="ingestion_jobs")
    metadata_records: Mapped[list["MetadataRecord"]] = relationship(
        "MetadataRecord",
        back_populates="ingestion_job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    classification_results: Mapped[list["ClassificationResult"]] = relationship(
        "ClassificationResult",
        back_populates="ingestion_job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    cost_records: Mapped[list["CostRecord"]] = relationship(
        "CostRecord",
        back_populates="ingestion_job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
