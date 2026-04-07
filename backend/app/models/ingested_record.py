from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import IngestionMethod


class IngestedRecord(Base):
    __tablename__ = "ingested_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "ingestion_method",
            "idempotency_key",
            name="uq_ingested_user_method_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    ingestion_method: Mapped[IngestionMethod] = mapped_column(Enum(IngestionMethod), index=True, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    external_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lineage_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_processed: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    api_key = relationship("APIKey")
    data_source = relationship("DataSource")
