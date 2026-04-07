from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, DataTemperature


class StorageRecord(Base):
    __tablename__ = "storage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)

    storage_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_savings: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    temperature: Mapped[DataTemperature] = mapped_column(Enum(DataTemperature), nullable=False)
    classification_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User", back_populates="storage_records")
