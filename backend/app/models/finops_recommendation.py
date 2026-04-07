from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DecisionState, OptimizationAction


class FinOpsRecommendation(Base):
    __tablename__ = "finops_recommendations"
    __table_args__ = (
        UniqueConstraint("resource_id", "recommendation_hash", name="uq_finops_recommendation_resource_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_pk: Mapped[int] = mapped_column(
        ForeignKey("finops_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recommendation_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[OptimizationAction] = mapped_column(Enum(OptimizationAction), nullable=False, index=True)
    decision_state: Mapped[DecisionState] = mapped_column(Enum(DecisionState), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    recommended_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False, index=True)
    recommended_storage_tier: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence_final: Mapped[float] = mapped_column(Float, nullable=False)
    rule_trace: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    resource = relationship("FinOpsResource", back_populates="recommendations")
