"""Celery tasks for background classification processing."""

from celery import shared_task

from app.core.database import AsyncSessionLocal
from app.modules.classification.service import ClassificationService


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_classification_batch(
    self,
    user_id: int,
    job_id: int | None = None,
    limit: int = 100,
) -> dict:
    """
    Process a batch of metadata records for classification.
    
    Args:
        user_id: ID of the user owning the records
        job_id: Optional ingestion job ID to filter records
        limit: Maximum number of records to classify
    
    Returns:
        Dict with classification results
    """
    async def _process():
        async with AsyncSessionLocal() as db:
            service = ClassificationService(db)
            result = await service.classify_batch(user_id, job_id, limit)
            return result
    
    import asyncio
    try:
        return asyncio.run(_process())
    except Exception as exc:
        # Retry on transient failures
        try:
            self.retry(exc=exc)
        except Exception:
            return {
                'status': 'failed',
                'error': str(exc),
                'retries_exhausted': True,
            }


@shared_task
def auto_classify_new_ingestion(ingestion_job_id: int) -> dict:
    """
    Automatically classify all records from a newly completed ingestion job.
    
    This task is triggered after ingestion job completion.
    """
    async def _classify():
        async with AsyncSessionLocal() as db:
            from app.modules.ingestion.repository import IngestionJobRepository
            
            job_repo = IngestionJobRepository(db)
            job = await job_repo.get_by_id(ingestion_job_id, ingestion_job_id)
            
            if not job:
                return {'error': f'Job {ingestion_job_id} not found'}
            
            service = ClassificationService(db)
            result = await service.classify_batch(
                job.user_id,
                job.id,
                limit=10000,  # Process all records in the job
            )
            
            return {
                'job_id': ingestion_job_id,
                'user_id': job.user_id,
                'classification_result': result,
            }
    
    import asyncio
    return asyncio.run(_classify())
