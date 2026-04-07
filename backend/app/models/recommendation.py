from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, RecommendationStatus


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("resource_name", "dataset_id", name="uq_recommendations_resource_dataset"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    recommended_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    recommended_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)

    estimated_monthly_savings: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), nullable=False, default=RecommendationStatus.OPEN
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="recommendations")
    ingestion_job = relationship("IngestionJob")
