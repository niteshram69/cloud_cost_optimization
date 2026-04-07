"""Database access layer for cost operations."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cost.models import Benchmark, CostRecord


class CostRepository:
    """Repository for cost record operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, cost_id: int, user_id: int) -> CostRecord | None:
        """Get cost record by ID."""
        result = await self.db.execute(
            select(CostRecord).where(
                CostRecord.id == cost_id,
                CostRecord.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_job(
        self,
        job_id: int,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> list[CostRecord]:
        """List cost records for an ingestion job."""
        result = await self.db.execute(
            select(CostRecord)
            .where(
                CostRecord.ingestion_job_id == job_id,
                CostRecord.user_id == user_id
            )
            .order_by(CostRecord.period_start.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def list_by_user(
        self,
        user_id: int,
        provider: str | None = None,
        service_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[CostRecord]:
        """List cost records with filters."""
        query = select(CostRecord).where(CostRecord.user_id == user_id)
        
        if provider:
            query = query.where(CostRecord.provider == provider)
        if service_type:
            query = query.where(CostRecord.service_type == service_type)
        if start_date:
            query = query.where(CostRecord.period_start >= start_date)
        if end_date:
            query = query.where(CostRecord.period_end <= end_date)
        
        result = await self.db.execute(
            query.order_by(CostRecord.period_start.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, cost_record: CostRecord) -> CostRecord:
        """Create a new cost record."""
        self.db.add(cost_record)
        await self.db.flush()
        await self.db.refresh(cost_record)
        return cost_record
    
    async def get_summary(
        self,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Get cost summary grouped by provider, service, and region."""
        query = select(CostRecord).where(CostRecord.user_id == user_id)
        
        if start_date:
            query = query.where(CostRecord.period_start >= start_date)
        if end_date:
            query = query.where(CostRecord.period_end <= end_date)
        
        result = await self.db.execute(query)
        records = result.scalars().all()
        
        if not records:
            return {
                'total_cost': Decimal('0'),
                'currency': 'USD',
                'by_provider': {},
                'by_service': {},
                'by_region': {},
                'record_count': 0,
            }
        
        total = sum(r.cost_amount for r in records)
        currency = records[0].currency if records else 'USD'
        
        by_provider: dict[str, Decimal] = {}
        by_service: dict[str, Decimal] = {}
        by_region: dict[str, Decimal] = {}
        
        for r in records:
            by_provider[r.provider] = by_provider.get(r.provider, Decimal('0')) + r.cost_amount
            by_service[r.service_type] = by_service.get(r.service_type, Decimal('0')) + r.cost_amount
            region = r.region or 'unknown'
            by_region[region] = by_region.get(region, Decimal('0')) + r.cost_amount
        
        return {
            'total_cost': total,
            'currency': currency,
            'by_provider': by_provider,
            'by_service': by_service,
            'by_region': by_region,
            'record_count': len(records),
        }


class BenchmarkRepository:
    """Repository for benchmark operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, benchmark_id: int) -> Benchmark | None:
        """Get benchmark by ID."""
        result = await self.db.execute(
            select(Benchmark).where(Benchmark.id == benchmark_id)
        )
        return result.scalar_one_or_none()
    
    async def list_available(
        self,
        user_id: int,
        service_type: str | None = None,
        provider: str | None = None,
    ) -> list[Benchmark]:
        """List available benchmarks (global or user-specific)."""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        
        query = select(Benchmark).where(
            (Benchmark.user_id == user_id) | (Benchmark.user_id == None),
            Benchmark.is_active == True,
            Benchmark.valid_from <= now,
            (Benchmark.valid_until == None) | (Benchmark.valid_until >= now)
        )
        
        if service_type:
            query = query.where(Benchmark.service_type == service_type)
        if provider:
            query = query.where(Benchmark.provider == provider)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def find_matching(
        self,
        user_id: int,
        service_type: str,
        provider: str,
        region: str | None = None,
    ) -> Benchmark | None:
        """Find best matching benchmark for criteria."""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        
        query = select(Benchmark).where(
            (Benchmark.user_id == user_id) | (Benchmark.user_id == None),
            Benchmark.service_type == service_type,
            Benchmark.provider == provider,
            Benchmark.is_active == True,
            Benchmark.valid_from <= now,
            (Benchmark.valid_until == None) | (Benchmark.valid_until >= now)
        )
        
        if region:
            query = query.where(
                (Benchmark.region == region) | (Benchmark.region == None)
            )
        
        # Order by specificity (user-specific first, then region-specific)
        query = query.order_by(
            Benchmark.user_id.nulls_last(),
            Benchmark.region.nulls_last(),
        )
        
        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none()
    
    async def create(self, benchmark: Benchmark) -> Benchmark:
        """Create a new benchmark."""
        self.db.add(benchmark)
        await self.db.flush()
        await self.db.refresh(benchmark)
        return benchmark
    
    async def delete(self, benchmark: Benchmark) -> None:
        """Delete a benchmark."""
        await self.db.delete(benchmark)
        await self.db.flush()
