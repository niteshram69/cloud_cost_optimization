"""Database access layer for metadata operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.metadata.models import MetadataRecord


class MetadataRepository:
    """Repository for metadata record operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, record_id: int, user_id: int) -> MetadataRecord | None:
        """Get metadata record by ID and user ID."""
        result = await self.db.execute(
            select(MetadataRecord).where(
                MetadataRecord.id == record_id,
                MetadataRecord.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_job(
        self,
        job_id: int,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> list[MetadataRecord]:
        """List metadata records for an ingestion job."""
        result = await self.db.execute(
            select(MetadataRecord)
            .where(
                MetadataRecord.ingestion_job_id == job_id,
                MetadataRecord.user_id == user_id
            )
            .order_by(MetadataRecord.discovered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def list_by_user(
        self,
        user_id: int,
        entity_type: str | None = None,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[MetadataRecord]:
        """List metadata records for a user with optional filters."""
        query = select(MetadataRecord).where(MetadataRecord.user_id == user_id)
        
        if entity_type:
            query = query.where(MetadataRecord.entity_type == entity_type)
        if provider:
            query = query.where(MetadataRecord.provider == provider)
        
        result = await self.db.execute(
            query.order_by(MetadataRecord.discovered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def count_by_user(
        self,
        user_id: int,
        entity_type: str | None = None,
        provider: str | None = None
    ) -> int:
        """Count metadata records for a user."""
        query = select(func.count(MetadataRecord.id)).where(
            MetadataRecord.user_id == user_id
        )
        
        if entity_type:
            query = query.where(MetadataRecord.entity_type == entity_type)
        if provider:
            query = query.where(MetadataRecord.provider == provider)
        
        result = await self.db.execute(query)
        return result.scalar() or 0
    
    async def create(self, metadata_record: MetadataRecord) -> MetadataRecord:
        """Create a new metadata record."""
        self.db.add(metadata_record)
        await self.db.flush()
        await self.db.refresh(metadata_record)
        return metadata_record
    
    async def delete(self, metadata_record: MetadataRecord) -> None:
        """Delete a metadata record."""
        await self.db.delete(metadata_record)
        await self.db.flush()
    
    async def get_providers_summary(self, user_id: int) -> list[dict]:
        """Get summary of providers and their resource counts."""
        result = await self.db.execute(
            select(
                MetadataRecord.provider,
                MetadataRecord.entity_type,
                func.count(MetadataRecord.id).label('count')
            )
            .where(MetadataRecord.user_id == user_id)
            .group_by(MetadataRecord.provider, MetadataRecord.entity_type)
        )
        
        rows = result.all()
        return [
            {
                'provider': row.provider,
                'entity_type': row.entity_type,
                'count': row.count,
            }
            for row in rows
        ]
