from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import AccountState


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    account_state: Mapped[AccountState] = mapped_column(
        Enum(AccountState),
        default=AccountState.TRIAL,
        index=True,
        nullable=False,
    )
    billing_currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    billing_region: Mapped[str] = mapped_column(String(32), default="IN", nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User")
    plan = relationship("Plan", back_populates="user_accounts")
