from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import UsageBucket


class UsageAggregate(Base):
    __tablename__ = "usage_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "api_key_id",
            "endpoint",
            "bucket_start",
            "bucket",
            name="uq_usage_aggregate_bucket",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    bucket: Mapped[UsageBucket] = mapped_column(Enum(UsageBucket), index=True, nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_volume_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compute_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User")
    api_key = relationship("APIKey")
