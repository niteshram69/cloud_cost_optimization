"""Database access layer for classification operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classification.models import ClassificationResult


class ClassificationRepository:
    """Repository for classification result operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, result_id: int, user_id: int) -> ClassificationResult | None:
        """Get classification result by ID."""
        result = await self.db.execute(
            select(ClassificationResult).where(
                ClassificationResult.id == result_id,
                ClassificationResult.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_metadata(
        self,
        metadata_record_id: int,
        user_id: int
    ) -> ClassificationResult | None:
        """Get classification for a specific metadata record."""
        result = await self.db.execute(
            select(ClassificationResult).where(
                ClassificationResult.metadata_record_id == metadata_record_id,
                ClassificationResult.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_job(
        self,
        job_id: int,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> list[ClassificationResult]:
        """List classification results for an ingestion job."""
        result = await self.db.execute(
            select(ClassificationResult)
            .where(
                ClassificationResult.ingestion_job_id == job_id,
                ClassificationResult.user_id == user_id
            )
            .order_by(ClassificationResult.classified_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def list_by_user(
        self,
        user_id: int,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[ClassificationResult]:
        """List classification results for a user with optional filters."""
        query = select(ClassificationResult).where(
            ClassificationResult.user_id == user_id
        )
        
        if category:
            query = query.where(ClassificationResult.category == category)
        
        result = await self.db.execute(
            query.order_by(ClassificationResult.classified_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, classification: ClassificationResult) -> ClassificationResult:
        """Create a new classification result."""
        self.db.add(classification)
        await self.db.flush()
        await self.db.refresh(classification)
        return classification
    
    async def update(self, classification: ClassificationResult) -> ClassificationResult:
        """Update a classification result."""
        await self.db.flush()
        await self.db.refresh(classification)
        return classification
    
    async def get_statistics(self, user_id: int) -> dict:
        """Get classification statistics for a user."""
        # Count by category
        cat_result = await self.db.execute(
            select(
                ClassificationResult.category,
                func.count(ClassificationResult.id).label('count')
            )
            .where(ClassificationResult.user_id == user_id)
            .group_by(ClassificationResult.category)
        )
        by_category = {row.category: row.count for row in cat_result.all()}
        
        # Count by method
        method_result = await self.db.execute(
            select(
                ClassificationResult.method,
                func.count(ClassificationResult.id).label('count')
            )
            .where(ClassificationResult.user_id == user_id)
            .group_by(ClassificationResult.method)
        )
        by_method = {row.method: row.count for row in method_result.all()}
        
        # Average confidence
        avg_conf = await self.db.execute(
            select(func.avg(ClassificationResult.confidence))
            .where(ClassificationResult.user_id == user_id)
        )
        avg_confidence = avg_conf.scalar() or 0.0
        
        # Total classified
        total = sum(by_category.values())
        
        return {
            'total_classified': total,
            'by_category': by_category,
            'by_method': by_method,
            'average_confidence': round(avg_confidence, 2),
        }
    
    async def count_unclassified(self, user_id: int, job_id: int | None = None) -> int:
        """Count metadata records without classification."""
        from app.modules.metadata.models import MetadataRecord
        
        query = select(func.count(MetadataRecord.id)).where(
            MetadataRecord.user_id == user_id,
            ~MetadataRecord.id.in_(
                select(ClassificationResult.metadata_record_id)
                .where(ClassificationResult.user_id == user_id)
            )
        )
        
        if job_id:
            query = query.where(MetadataRecord.ingestion_job_id == job_id)
        
        result = await self.db.execute(query)
        return result.scalar() or 0
