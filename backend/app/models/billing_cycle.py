from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import BillingCycleStatus


class BillingCycle(Base):
    __tablename__ = "billing_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    status: Mapped[BillingCycleStatus] = mapped_column(
        Enum(BillingCycleStatus),
        default=BillingCycleStatus.OPEN,
        index=True,
        nullable=False,
    )
    included_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    overage_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User")
    plan = relationship("Plan", back_populates="billing_cycles")
    invoices = relationship("Invoice", back_populates="billing_cycle")
