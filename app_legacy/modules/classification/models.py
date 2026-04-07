"""Classification module database models."""

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ClassificationCategory
from app.core.database import Base


class ClassificationResult(Base):
    """Classification results for metadata records."""
    
    __tablename__ = "classification_results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # References
    ingestion_job_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metadata_record_id: Mapped[int] = mapped_column(
        ForeignKey("metadata_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Classification result
    category: Mapped[str] = mapped_column(
        String(20),
        default=ClassificationCategory.UNKNOWN.value,
        nullable=False,
        index=True,
    )
    # sensitivity: 'high', 'medium', 'low'
    # relevance: 'critical', 'important', 'optional'
    # cost_category: 'compute', 'storage', 'network', 'license'
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 0.0 to 1.0
    # Classification method
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'rule_based', 'ml_model', 'manual', 'hybrid'
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Model identifier for ML-based classifications
    # Rule/explanation
    rules_applied: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of rule names that triggered
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Human-readable explanation of classification
    # Manual override
    is_manual: Mapped[bool] = mapped_column(default=False, nullable=False)
    manual_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    manual_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manual_at: Mapped[datetime | None] = mapped_column(nullable=True)
    manual_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Timestamps
    classified_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reclassified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Relationships
    ingestion_job: Mapped["IngestionJob"] = relationship("IngestionJob", back_populates="classification_results")
    metadata_record: Mapped["MetadataRecord"] = relationship("MetadataRecord", back_populates="classification_results")
