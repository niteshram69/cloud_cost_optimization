from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    data_volume_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compute_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user = relationship("User")
    api_key = relationship("APIKey")
