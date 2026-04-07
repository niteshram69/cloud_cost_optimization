"""Pydantic schemas for ingestion requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import IngestionStatus


# Data Source schemas
class DataSourceBase(BaseModel):
    """Base data source schema."""
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., pattern="^(s3|api|upload|gcs|azure)$")
    config: dict = Field(default_factory=dict)
    schedule: str | None = None  # Cron expression


class DataSourceCreateRequest(DataSourceBase):
    """Request to create a data source."""
    pass


class DataSourceResponse(DataSourceBase):
    """Response with data source details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    is_active: bool
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


# Ingestion Job schemas
class IngestionJobResponse(BaseModel):
    """Response with ingestion job details."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: int
    data_source_id: int | None
    status: str
    file_name: str
    file_size: int
    mime_type: str
    checksum: str | None
    metadata: dict = Field(..., alias="job_metadata")
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    celery_task_id: str | None
    created_at: datetime


class IngestionJobListResponse(BaseModel):
    """Response for listing ingestion jobs."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    status: str
    file_name: str
    file_size: int
    created_at: datetime
    completed_at: datetime | None


# File upload schemas
class FileUploadResponse(BaseModel):
    """Response after file upload."""
    job_id: int
    file_name: str
    file_size: int
    status: str
    message: str


class ProcessingStatusResponse(BaseModel):
    """Response with processing status."""
    job_id: int
    status: str
    progress: dict  # {stage, percent, details}
    result: dict | None
    error: str | None
