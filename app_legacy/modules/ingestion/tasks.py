"""Celery tasks for background ingestion processing."""

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from app.core.constants import IngestionStatus
from app.core.database import AsyncSessionLocal
from app.modules.ingestion.repository import IngestionJobRepository
from app.modules.ingestion.service import IngestionService
from celery_worker import celery_app


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_ingestion_job(self, job_id: int) -> dict:
    """
    Process an ingestion job asynchronously.
    
    Args:
        job_id: ID of the IngestionJob to process
    
    Returns:
        Dict with processing results
    """
    async def _process():
        async with AsyncSessionLocal() as db:
            service = IngestionService(db)
            try:
                result = await service.process_job(job_id)
                return result
            except Exception as exc:
                # Update job status to failed
                job_repo = IngestionJobRepository(db)
                await job_repo.update_status(
                    job_id,
                    IngestionStatus.FAILED.value,
                    error_message=str(exc)
                )
                raise exc
    
    import asyncio
    try:
        return asyncio.run(_process())
    except Exception as exc:
        # Retry on failure
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            return {
                'status': 'failed',
                'error': str(exc),
                'retries_exhausted': True,
            }


@shared_task
def cleanup_old_data(retention_days: int = 90) -> dict:
    """
    Clean up old ingestion data based on retention policy.
    
    Args:
        retention_days: Number of days to retain data
    
    Returns:
        Dict with cleanup statistics
    """
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            from datetime import datetime, timedelta, timezone
            from sqlalchemy import delete, select
            from app.modules.ingestion.models import IngestionJob
            
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
            
            # Find old completed/failed jobs
            result = await db.execute(
                select(IngestionJob).where(
                    IngestionJob.created_at < cutoff_date,
                    IngestionJob.status.in_(['completed', 'failed'])
                )
            )
            old_jobs = result.scalars().all()
            
            jobs_deleted = 0
            files_removed = 0
            
            for job in old_jobs:
                # Delete associated file
                if job.file_path:
                    import os
                    try:
                        if os.path.exists(job.file_path):
                            os.remove(job.file_path)
                            files_removed += 1
                    except OSError:
                        pass  # File may not exist or permission denied
                
                await db.delete(job)
                jobs_deleted += 1
            
            await db.commit()
            
            return {
                'jobs_deleted': jobs_deleted,
                'files_removed': files_removed,
                'retention_days': retention_days,
                'cutoff_date': cutoff_date.isoformat(),
            }
    
    import asyncio
    return asyncio.run(_cleanup())
