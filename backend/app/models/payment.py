from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import PaymentProvider, PaymentStatus


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), index=True, nullable=True)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider), index=True, nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    raw_event: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User")
    invoice = relationship("Invoice", back_populates="payments")
