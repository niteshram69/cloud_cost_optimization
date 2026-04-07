"""Business logic for classification operations."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ClassificationCategory
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.modules.classification.engine import ClassificationEngine
from app.modules.classification.models import ClassificationResult
from app.modules.classification.repository import ClassificationRepository
from app.modules.classification.schemas import (
    ClassificationStatsResponse,
    ManualClassificationRequest,
)
from app.modules.metadata.models import MetadataRecord
from app.modules.metadata.repository import MetadataRepository


class ClassificationService:
    """Service for managing resource classification."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ClassificationRepository(db)
        self.metadata_repo = MetadataRepository(db)
        self.engine = ClassificationEngine()
    
    async def classify_metadata_record(
        self,
        user_id: int,
        metadata_record_id: int,
    ) -> ClassificationResult:
        """Classify a single metadata record."""
        # Check if metadata record exists
        metadata = await self.metadata_repo.get_by_id(metadata_record_id, user_id)
        if not metadata:
            raise ResourceNotFoundError("Metadata Record", str(metadata_record_id))
        
        # Check if already classified
        existing = await self.repo.get_by_metadata(metadata_record_id, user_id)
        if existing and not existing.is_manual:
            # Reclassify (update existing)
            classification = existing
        else:
            # Create new classification
            classification = ClassificationResult(
                ingestion_job_id=metadata.ingestion_job_id,
                metadata_record_id=metadata_record_id,
                user_id=user_id,
            )
        
        # Run classification
        result = self.engine.classify({
            'entity_type': metadata.entity_type,
            'entity_id': metadata.entity_id,
            'provider': metadata.provider,
            'region': metadata.region,
            'account_id': metadata.account_id,
            'attributes': metadata.attributes,
            'tags': metadata.tags,
            'resource_updated_at': metadata.resource_updated_at.isoformat() if metadata.resource_updated_at else None,
            'discovered_at': metadata.discovered_at.isoformat() if metadata.discovered_at else None,
        })
        
        # Update classification record
        classification.category = result['category']
        classification.confidence = result['confidence']
        classification.method = result['method']
        classification.model_version = result['model_version']
        classification.rules_applied = ','.join(result['rules_applied']) if result['rules_applied'] else None
        classification.explanation = result['explanation']
        classification.is_manual = False
        classification.classified_at = datetime.now(timezone.utc)
        
        if existing:
            await self.repo.update(classification)
        else:
            classification = await self.repo.create(classification)
        
        return classification
    
    async def classify_batch(
        self,
        user_id: int,
        job_id: int | None = None,
        limit: int = 100,
    ) -> dict:
        """Classify a batch of unclassified metadata records."""
        # Get unclassified records
        from sqlalchemy import select
        
        query = select(MetadataRecord).where(
            MetadataRecord.user_id == user_id,
            ~MetadataRecord.id.in_(
                select(ClassificationResult.metadata_record_id)
                .where(ClassificationResult.user_id == user_id)
            )
        )
        
        if job_id:
            query = query.where(MetadataRecord.ingestion_job_id == job_id)
        
        query = query.limit(limit)
        
        result = await self.db.execute(query)
        records = result.scalars().all()
        
        if not records:
            return {
                'processed': 0,
                'classified': 0,
                'errors': 0,
                'message': 'No unclassified records found',
            }
        
        # Classify each record
        classified_count = 0
        error_count = 0
        
        for metadata in records:
            try:
                await self.classify_metadata_record(user_id, metadata.id)
                classified_count += 1
            except Exception:
                error_count += 1
        
        await self.db.commit()
        
        return {
            'processed': len(records),
            'classified': classified_count,
            'errors': error_count,
        }
    
    async def manual_classify(
        self,
        user_id: int,
        metadata_record_id: int,
        data: ManualClassificationRequest,
        classified_by: str,
    ) -> ClassificationResult:
        """Manually classify a metadata record."""
        # Check if metadata record exists
        metadata = await self.metadata_repo.get_by_id(metadata_record_id, user_id)
        if not metadata:
            raise ResourceNotFoundError("Metadata Record", str(metadata_record_id))
        
        # Get existing classification or create new
        existing = await self.repo.get_by_metadata(metadata_record_id, user_id)
        
        if existing:
            classification = existing
            classification.reclassified_at = datetime.now(timezone.utc)
        else:
            classification = ClassificationResult(
                ingestion_job_id=metadata.ingestion_job_id,
                metadata_record_id=metadata_record_id,
                user_id=user_id,
            )
        
        # Apply manual classification
        classification.category = data.category
        classification.confidence = 1.0  # Manual classification has full confidence
        classification.method = 'manual'
        classification.is_manual = True
        classification.manual_category = data.category
        classification.manual_by = classified_by
        classification.manual_at = datetime.now(timezone.utc)
        classification.manual_reason = data.reason
        classification.explanation = f"Manually classified by {classified_by}"
        classification.classified_at = datetime.now(timezone.utc)
        
        if existing:
            await self.repo.update(classification)
        else:
            classification = await self.repo.create(classification)
        
        return classification
    
    async def get_classification(
        self,
        user_id: int,
        classification_id: int,
    ) -> ClassificationResult:
        """Get a classification result."""
        classification = await self.repo.get_by_id(classification_id, user_id)
        if not classification:
            raise ResourceNotFoundError("Classification Result", str(classification_id))
        return classification
    
    async def list_classifications(
        self,
        user_id: int,
        job_id: int | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClassificationResult]:
        """List classification results."""
        if job_id:
            return await self.repo.list_by_job(job_id, user_id, limit, offset)
        else:
            return await self.repo.list_by_user(user_id, category, limit, offset)
    
    async def get_statistics(self, user_id: int) -> ClassificationStatsResponse:
        """Get classification statistics."""
        stats = await self.repo.get_statistics(user_id)
        pending = await self.repo.count_unclassified(user_id)
        
        return ClassificationStatsResponse(
            total_classified=stats['total_classified'],
            by_category=stats['by_category'],
            by_method=stats['by_method'],
            average_confidence=stats['average_confidence'],
            pending_classification=pending,
        )
    
    async def get_classification_by_metadata(
        self,
        user_id: int,
        metadata_record_id: int,
    ) -> ClassificationResult | None:
        """Get classification for a specific metadata record."""
        return await self.repo.get_by_metadata(metadata_record_id, user_id)
