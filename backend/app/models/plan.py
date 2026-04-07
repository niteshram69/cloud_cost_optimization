from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import PlanCode


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[PlanCode] = mapped_column(Enum(PlanCode), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    base_monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    included_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    overage_price_per_request: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user_accounts = relationship("UserAccount", back_populates="plan")
    billing_cycles = relationship("BillingCycle", back_populates="plan")
    subscriptions = relationship("Subscription", back_populates="plan")
