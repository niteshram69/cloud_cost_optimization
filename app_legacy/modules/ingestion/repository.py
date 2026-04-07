"""Database access layer for ingestion operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ingestion.models import DataSource, IngestionJob


class DataSourceRepository:
    """Repository for data source operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, source_id: int, user_id: int) -> DataSource | None:
        """Get data source by ID and user ID."""
        result = await self.db.execute(
            select(DataSource).where(
                DataSource.id == source_id,
                DataSource.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_user(self, user_id: int) -> list[DataSource]:
        """List all data sources for a user."""
        result = await self.db.execute(
            select(DataSource)
            .where(DataSource.user_id == user_id)
            .order_by(DataSource.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def create(self, data_source: DataSource) -> DataSource:
        """Create a new data source."""
        self.db.add(data_source)
        await self.db.flush()
        await self.db.refresh(data_source)
        return data_source
    
    async def delete(self, data_source: DataSource) -> None:
        """Delete a data source."""
        await self.db.delete(data_source)
        await self.db.flush()
    
    async def update(self, data_source: DataSource) -> DataSource:
        """Update a data source."""
        await self.db.flush()
        await self.db.refresh(data_source)
        return data_source


class IngestionJobRepository:
    """Repository for ingestion job operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, job_id: int, user_id: int) -> IngestionJob | None:
        """Get ingestion job by ID and user ID."""
        result = await self.db.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list[IngestionJob]:
        """List ingestion jobs for a user with pagination."""
        result = await self.db.execute(
            select(IngestionJob)
            .where(IngestionJob.user_id == user_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, job: IngestionJob) -> IngestionJob:
        """Create a new ingestion job."""
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job
    
    async def update(self, job: IngestionJob) -> IngestionJob:
        """Update an ingestion job."""
        await self.db.flush()
        await self.db.refresh(job)
        return job
    
    async def update_status(
        self,
        job_id: int,
        status: str,
        metadata: dict | None = None,
        error_message: str | None = None
    ) -> None:
        """Update job status."""
        from datetime import datetime, timezone
        
        job = await self.db.get(IngestionJob, job_id)
        if job:
            job.status = status
            if metadata:
                job.job_metadata.update(metadata)
            if error_message:
                job.error_message = error_message
            if status == "processing":
                job.started_at = datetime.now(timezone.utc)
            if status in ["completed", "failed"]:
                job.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
