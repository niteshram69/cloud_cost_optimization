"""Ingestion API routes for file upload and data source management."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.dependencies import CurrentUserDependency
from app.modules.ingestion.schemas import (
    DataSourceCreateRequest,
    DataSourceResponse,
    FileUploadResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    ProcessingStatusResponse,
)
from app.modules.ingestion.service import IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    data_source_id: int | None = Form(None),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file for ingestion (CSV, JSON billing exports).
    Max file size: 100MB
    """
    # Validate file size
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB",
        )
    
    # Validate file type
    allowed_types = [
        'text/csv',
        'application/json',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain',
        'application/gzip',
        'application/zip',
    ]
    
    # Check both declared type and content
    if file.content_type not in allowed_types:
        # Additional check by file extension
        filename_lower = file.filename.lower()
        if not any(filename_lower.endswith(ext) for ext in ['.csv', '.json', '.xlsx', '.xls', '.gz', '.zip', '.txt']):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: {file.content_type}. Allowed: CSV, JSON, Excel, GZIP, ZIP",
            )
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    unique_filename = f"{file_id}{file_ext}"
    file_path = Path(settings.UPLOAD_DIR) / unique_filename
    
    # Ensure upload directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Create ingestion job
    service = IngestionService(db)
    job = await service.process_file_upload(
        user_id=int(current_user["id"]),
        file_path=str(file_path),
        original_filename=file.filename,
        mime_type=file.content_type or 'application/octet-stream',
        file_size=file_size,
    )
    
    return FileUploadResponse(
        job_id=job.id,
        file_name=file.filename,
        file_size=file_size,
        status=job.status,
        message="File uploaded successfully. Processing in background.",
    )


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
async def get_job_status(
    job_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed status of an ingestion job."""
    service = IngestionService(db)
    job = await service.get_job_status(int(current_user["id"]), job_id)
    return job


@router.get("/jobs", response_model=list[IngestionJobListResponse])
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """List ingestion jobs for current user."""
    service = IngestionService(db)
    jobs = await service.list_jobs(int(current_user["id"]), limit, offset)
    return jobs


# Data Source management endpoints
@router.post("/sources", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data: DataSourceCreateRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Create a new data source configuration."""
    service = IngestionService(db)
    source = await service.create_data_source(int(current_user["id"]), data)
    return source


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_data_sources(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """List configured data sources for current user."""
    service = IngestionService(db)
    sources = await service.list_data_sources(int(current_user["id"]))
    return sources


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Delete a data source configuration."""
    service = IngestionService(db)
    await service.delete_data_source(int(current_user["id"]), source_id)
