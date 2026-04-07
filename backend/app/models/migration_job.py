from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import CloudProvider, MigrationStatus


class MigrationJob(Base):
    __tablename__ = "migration_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)
    target_provider: Mapped[CloudProvider] = mapped_column(Enum(CloudProvider), nullable=False)

    status: Mapped[MigrationStatus] = mapped_column(Enum(MigrationStatus), nullable=False, default=MigrationStatus.PENDING)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="migrations")
