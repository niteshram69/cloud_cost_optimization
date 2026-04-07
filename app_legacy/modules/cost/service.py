"""Business logic for cost analysis and benchmarking."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.modules.cost.analyzer import CostAnalyzer
from app.modules.cost.models import Benchmark, CostRecord
from app.modules.cost.repository import BenchmarkRepository, CostRepository
from app.modules.cost.schemas import (
    BenchmarkCreateRequest,
    CostComparisonRequest,
    CostComparisonResult,
    CostSummaryResponse,
    CostTrendResponse,
)


class CostService:
    """Service for cost analysis and benchmarking operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cost_repo = CostRepository(db)
        self.benchmark_repo = BenchmarkRepository(db)
        self.analyzer = CostAnalyzer()
    
    async def get_cost_records(
        self,
        user_id: int,
        provider: str | None = None,
        service_type: str | None = None,
        months: int = 1,
        limit: int = 100,
        offset: int = 0
    ) -> list[CostRecord]:
        """Get cost records with optional filtering."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)
        
        return await self.cost_repo.list_by_user(
            user_id,
            provider,
            service_type,
            start_date,
            end_date,
            limit,
            offset
        )
    
    async def get_cost_summary(
        self,
        user_id: int,
        months: int = 1,
    ) -> CostSummaryResponse:
        """Get summary of costs over a period."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)
        
        summary = await self.cost_repo.get_summary(user_id, start_date, end_date)
        
        return CostSummaryResponse(
            total_cost=summary['total_cost'],
            currency=summary['currency'],
            period_start=start_date,
            period_end=end_date,
            by_provider=summary['by_provider'],
            by_service=summary['by_service'],
            by_region=summary['by_region'],
            record_count=summary['record_count'],
        )
    
    async def get_cost_trends(
        self,
        user_id: int,
        months: int = 6,
        granularity: str = 'monthly',
    ) -> CostTrendResponse:
        """Get cost trends over time."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)
        
        records = await self.cost_repo.list_by_user(
            user_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )
        
        trends = self.analyzer.calculate_trends(records, granularity)
        
        return CostTrendResponse(
            period=granularity,
            data_points=trends,
        )
    
    async def compare_costs(
        self,
        user_id: int,
        request: CostComparisonRequest,
    ) -> list[CostComparisonResult]:
        """Compare costs against benchmarks."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * request.period_months)
        
        # Get cost records
        records = await self.cost_repo.list_by_user(
            user_id,
            service_type=request.service_type,
            start_date=start_date,
            end_date=end_date,
            limit=1000,
        )
        
        # Filter by resource_id if specified
        if request.resource_id:
            records = [r for r in records if r.resource_id == request.resource_id]
        
        if not records:
            return []
        
        # Get benchmarks for comparison
        results = []
        for record in records:
            benchmark = await self.benchmark_repo.find_matching(
                user_id,
                record.service_type,
                record.provider,
                record.region,
            )
            
            comparison = self.analyzer.compare_to_benchmark(record, benchmark)
            unit_cost = self.analyzer.calculate_unit_cost(
                record.cost_amount,
                record.usage_quantity
            )
            
            results.append(CostComparisonResult(
                resource_id=record.resource_id,
                service_type=record.service_type,
                provider=record.provider,
                current_cost=record.cost_amount,
                current_unit_cost=unit_cost,
                unit=record.usage_unit,
                benchmark_avg=comparison['benchmark_avg'],
                benchmark_min=comparison['benchmark_min'],
                benchmark_max=comparison['benchmark_max'],
                variance_pct=comparison['variance_pct'],
                potential_savings=comparison['potential_savings'],
                comparison_status=comparison['comparison_status'],
            ))
        
        return results
    
    async def find_savings_opportunities(
        self,
        user_id: int,
        months: int = 1,
    ) -> list[dict]:
        """Find potential savings opportunities."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)
        
        # Get cost records
        records = await self.cost_repo.list_by_user(
            user_id,
            start_date=start_date,
            end_date=end_date,
            limit=1000,
        )
        
        # Get relevant benchmarks
        service_types = list(set(r.service_type for r in records))
        providers = list(set(r.provider for r in records))
        
        benchmarks = []
        for service_type in service_types:
            for provider in providers:
                b = await self.benchmark_repo.find_matching(
                    user_id, service_type, provider
                )
                if b:
                    benchmarks.append(b)
        
        return self.analyzer.find_savings_opportunities(records, benchmarks)
    
    async def detect_anomalies(
        self,
        user_id: int,
        threshold_pct: float = 50.0,
    ) -> list[dict]:
        """Detect cost anomalies."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=90)  # 3 months for baseline
        
        records = await self.cost_repo.list_by_user(
            user_id,
            start_date=start_date,
            end_date=end_date,
            limit=5000,
        )
        
        return self.analyzer.detect_anomalies(
            records,
            threshold_pct=threshold_pct,
        )
    
    # Benchmark management
    
    async def create_benchmark(
        self,
        user_id: int,
        data: BenchmarkCreateRequest,
    ) -> Benchmark:
        """Create a new benchmark."""
        benchmark = Benchmark(
            user_id=user_id,
            name=data.name,
            description=data.description,
            service_type=data.service_type,
            provider=data.provider,
            region=data.region,
            avg_cost_per_unit=data.avg_cost_per_unit,
            min_cost_per_unit=data.min_cost_per_unit,
            max_cost_per_unit=data.max_cost_per_unit,
            unit=data.unit,
            source=data.source,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
        )
        return await self.benchmark_repo.create(benchmark)
    
    async def list_benchmarks(
        self,
        user_id: int,
        service_type: str | None = None,
        provider: str | None = None,
    ) -> list[Benchmark]:
        """List available benchmarks."""
        return await self.benchmark_repo.list_available(
            user_id,
            service_type,
            provider,
        )
    
    async def delete_benchmark(self, user_id: int, benchmark_id: int) -> None:
        """Delete a benchmark."""
        benchmark = await self.benchmark_repo.get_by_id(benchmark_id)
        if not benchmark or benchmark.user_id != user_id:
            raise ResourceNotFoundError("Benchmark", str(benchmark_id))
        
        await self.benchmark_repo.delete(benchmark)
