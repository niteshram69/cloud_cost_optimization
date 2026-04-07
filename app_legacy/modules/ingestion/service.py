"""Business logic for data ingestion and file processing."""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import IngestionStatus
from app.core.exceptions import ProcessingError, ResourceNotFoundError, ValidationError
from app.modules.ingestion.models import DataSource, IngestionJob
from app.modules.ingestion.repository import DataSourceRepository, IngestionJobRepository
from app.modules.ingestion.schemas import DataSourceCreateRequest
from app.modules.metadata.collector import MetadataCollector
from app.modules.metadata.models import MetadataRecord


class IngestionService:
    """Service for managing data ingestion."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.source_repo = DataSourceRepository(db)
        self.job_repo = IngestionJobRepository(db)
        self.metadata_collector = MetadataCollector()
    
    async def create_data_source(
        self,
        user_id: int,
        data: DataSourceCreateRequest
    ) -> DataSource:
        """Create a new data source configuration."""
        # Validate config based on source_type
        self._validate_source_config(data.source_type, data.config)
        
        source = DataSource(
            user_id=user_id,
            name=data.name,
            source_type=data.source_type,
            config=data.config,
            schedule=data.schedule,
        )
        return await self.source_repo.create(source)
    
    def _validate_source_config(self, source_type: str, config: dict) -> None:
        """Validate data source configuration."""
        required_fields = {
            's3': ['bucket', 'region'],
            'gcs': ['bucket'],
            'azure': ['container', 'account_name'],
            'api': ['endpoint'],
        }
        
        required = required_fields.get(source_type, [])
        missing = [f for f in required if f not in config]
        
        if missing:
            raise ValidationError(
                f"Missing required config fields for {source_type}: {', '.join(missing)}"
            )
    
    async def list_data_sources(self, user_id: int) -> list[DataSource]:
        """List all data sources for a user."""
        return await self.source_repo.list_by_user(user_id)
    
    async def delete_data_source(self, user_id: int, source_id: int) -> None:
        """Delete a data source."""
        source = await self.source_repo.get_by_id(source_id, user_id)
        if not source:
            raise ResourceNotFoundError("Data Source", str(source_id))
        
        await self.source_repo.delete(source)
    
    async def process_file_upload(
        self,
        user_id: int,
        file_path: str,
        original_filename: str,
        mime_type: str,
        file_size: int,
    ) -> IngestionJob:
        """Process an uploaded file and create ingestion job."""
        # Create upload directory if needed
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Compute checksum
        checksum = self.metadata_collector.compute_checksum(file_path)
        
        # Create job record
        job = IngestionJob(
            user_id=user_id,
            data_source_id=None,  # Direct upload
            status=IngestionStatus.PENDING.value,
            file_path=file_path,
            file_name=original_filename,
            file_size=file_size,
            mime_type=mime_type,
            checksum=checksum,
            metadata={
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
            },
        )
        
        created_job = await self.job_repo.create(job)
        
        # Queue for background processing
        from app.modules.ingestion.tasks import process_ingestion_job
        task = process_ingestion_job.delay(created_job.id)
        
        # Update with task ID
        created_job.celery_task_id = task.id
        await self.job_repo.update(created_job)
        
        return created_job
    
    async def get_job_status(self, user_id: int, job_id: int) -> IngestionJob:
        """Get ingestion job status."""
        job = await self.job_repo.get_by_id(job_id, user_id)
        if not job:
            raise ResourceNotFoundError("Ingestion Job", str(job_id))
        return job
    
    async def list_jobs(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list[IngestionJob]:
        """List ingestion jobs for a user."""
        return await self.job_repo.list_by_user(user_id, limit, offset)
    
    async def process_job(self, job_id: int) -> dict:
        """Process an ingestion job (called by Celery worker)."""
        job = await self.job_repo.get_by_id(job_id, job_id)  # Will be fixed by actual user context
        if not job:
            raise ResourceNotFoundError("Ingestion Job", str(job_id))
        
        try:
            # Update status to processing
            await self.job_repo.update_status(job_id, IngestionStatus.PROCESSING.value)
            
            # Extract metadata
            records, info = self.metadata_collector.extract_metadata(
                job.file_path,
                job.mime_type,
                job.user_id,
                job.id
            )
            
            # Store metadata records
            stored_count = 0
            for record_data in records:
                metadata_record = MetadataRecord(**record_data)
                self.db.add(metadata_record)
                stored_count += 1
            
            await self.db.flush()
            
            # Update job with results
            await self.job_repo.update_status(
                job_id,
                IngestionStatus.COMPLETED.value,
                metadata={
                    'records_extracted': stored_count,
                    'providers_detected': info.get('providers_detected', []),
                    'entity_types': info.get('entity_types', []),
                }
            )
            
            return {
                'status': 'completed',
                'records_processed': stored_count,
                'info': info,
            }
            
        except Exception as e:
            await self.job_repo.update_status(
                job_id,
                IngestionStatus.FAILED.value,
                error_message=str(e)
            )
            raise ProcessingError(f"Job processing failed: {str(e)}")
    
    def cleanup_old_data(self, days: int) -> dict:
        """Clean up old ingestion jobs and associated files."""
        # This would be called by a scheduled task
        # For now, return a placeholder
        return {
            'jobs_deleted': 0,
            'files_removed': 0,
            'retention_days': days,
        }
