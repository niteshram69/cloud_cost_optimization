"""API schemas for v2 storage optimization platform."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.decision_engine.types import DecisionMode


class InventoryObjectInput(BaseModel):
    """Inventory metadata for one object."""

    tenant_id: str
    provider: str
    region: str
    bucket: str
    object_key: str
    storage_tier: str
    size_bytes: int = Field(ge=0)
    last_modified_at: datetime
    last_accessed_at: datetime | None = None
    etag: str | None = None
    growth_bytes_90d: int = 0


class AccessEventInput(BaseModel):
    """Normalized access event used for behavior reconstruction."""

    tenant_id: str
    provider: str
    region: str
    bucket: str
    object_key: str
    event_id: str
    operation: str
    timestamp: datetime
    bytes_transferred: int = Field(default=0, ge=0)


class OptimizationRequest(BaseModel):
    """Request body for dry-run/enforced optimization."""

    mode: DecisionMode = DecisionMode.DRY_RUN
    currency: str = "USD"
    ml_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    delete_source_after_migration: bool = False
    allowed_regions: dict[str, list[str]] = Field(default_factory=dict)
    inventory: list[InventoryObjectInput]
    access_events: list[AccessEventInput] = Field(default_factory=list)


class LabeledSampleInput(BaseModel):
    """Labeled feature row used for in-API model training."""

    tenant_id: str
    object_id: str
    provider: str
    region: str
    current_tier: str
    object_size_gb: float
    days_since_last_access: float
    access_frequency_30d: float
    access_frequency_90d: float
    read_write_ratio: float
    storage_growth_trend_gb_30d: float
    access_pattern_entropy: float
    read_count_30d: int
    write_count_30d: int
    read_count_90d: int
    write_count_90d: int
    label: str


class TrainModelRequest(BaseModel):
    """Request for training the ML layer with labeled samples."""

    samples: list[LabeledSampleInput]
    persist_model: bool = True


class TrainModelResponse(BaseModel):
    """ML training response."""

    model_version: str
    n_samples: int
    accuracy: float
    classes: list[str]


class OptimizationResponse(BaseModel):
    """Optimization batch response."""

    mode: str
    currency: str
    summary: dict
    decisions: list[dict]
