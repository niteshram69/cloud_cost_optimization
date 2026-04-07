"""Classification API routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import CurrentUserDependency
from app.modules.classification.schemas import (
    BatchClassificationRequest,
    ClassificationProgressResponse,
    ClassificationResultResponse,
    ClassificationStatsResponse,
    ManualClassificationRequest,
)
from app.modules.classification.service import ClassificationService

router = APIRouter(prefix="/classification", tags=["classification"])


@router.post("/classify/{metadata_record_id}", response_model=ClassificationResultResponse)
async def classify_record(
    metadata_record_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Classify a single metadata record."""
    service = ClassificationService(db)
    result = await service.classify_metadata_record(
        int(current_user["id"]),
        metadata_record_id,
    )
    return result


@router.post("/classify-batch", response_model=dict)
async def classify_batch(
    request: BatchClassificationRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Trigger classification for a batch of unclassified records."""
    # Queue background task
    from app.modules.classification.tasks import process_classification_batch
    
    task = process_classification_batch.delay(
        int(current_user["id"]),
        request.job_id,
        request.limit,
    )
    
    return {
        'task_id': task.id,
        'status': 'queued',
        'message': f'Classification batch queued for {request.limit} records',
    }


@router.post("/manual/{metadata_record_id}", response_model=ClassificationResultResponse)
async def manual_classify(
    metadata_record_id: int,
    data: ManualClassificationRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Manually classify a metadata record."""
    service = ClassificationService(db)
    result = await service.manual_classify(
        int(current_user["id"]),
        metadata_record_id,
        data,
        current_user["email"],
    )
    return result


@router.get("/results", response_model=list[ClassificationResultResponse])
async def list_classifications(
    job_id: int | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """List classification results."""
    service = ClassificationService(db)
    results = await service.list_classifications(
        int(current_user["id"]),
        job_id,
        category,
        limit,
        offset,
    )
    return results


@router.get("/results/{classification_id}", response_model=ClassificationResultResponse)
async def get_classification(
    classification_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific classification result."""
    service = ClassificationService(db)
    result = await service.get_classification(
        int(current_user["id"]),
        classification_id,
    )
    return result


@router.get("/stats", response_model=ClassificationStatsResponse)
async def get_statistics(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get classification statistics for current user."""
    service = ClassificationService(db)
    stats = await service.get_statistics(int(current_user["id"]))
    return stats
