from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import GovernanceRuleType


class GovernancePolicy(Base):
    __tablename__ = "governance_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "target_tag_key",
            "target_tag_value",
            "rule_type",
            name="uq_governance_policy_scope_rule",
        ),
        Index("idx_governance_policy_tenant", "tenant_id", "is_active"),
    )

    policy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    target_tag_key: Mapped[str] = mapped_column(String(64), nullable=False, default="Environment")
    target_tag_value: Mapped[str | None] = mapped_column(String(64), nullable=True)

    rule_type: Mapped[GovernanceRuleType] = mapped_column(Enum(GovernanceRuleType), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    rule_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_by_user = relationship("User")
