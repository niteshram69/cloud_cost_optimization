"""Pydantic schemas for classification requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClassificationResultResponse(BaseModel):
    """Response with classification result details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    metadata_record_id: int
    category: str
    confidence: float
    method: str
    model_version: str | None
    rules_applied: str | None
    explanation: str | None
    is_manual: bool
    classified_at: datetime


class ClassificationStatsResponse(BaseModel):
    """Classification statistics for a user's data."""
    total_classified: int
    by_category: dict[str, int]
    by_method: dict[str, int]
    average_confidence: float
    pending_classification: int


class ManualClassificationRequest(BaseModel):
    """Request to manually classify a metadata record."""
    category: str = Field(..., pattern="^(sensitive|internal|public|archive|unknown)$")
    reason: str | None = None


class BatchClassificationRequest(BaseModel):
    """Request to trigger classification for unclassified records."""
    job_id: int | None = None  # Classify all records from a specific job
    limit: int = Field(default=100, ge=1, le=1000)


class ClassificationProgressResponse(BaseModel):
    """Response with classification batch progress."""
    task_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    total_records: int
    processed: int
    failed: int
    estimated_completion: datetime | None
