"""Cost analysis API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import CurrentUserDependency
from app.modules.cost.schemas import (
    BenchmarkCreateRequest,
    BenchmarkResponse,
    CostComparisonRequest,
    CostComparisonResult,
    CostRecordResponse,
    CostSummaryResponse,
    CostTrendResponse,
)
from app.modules.cost.service import CostService

router = APIRouter(prefix="/cost", tags=["cost-analysis"])


@router.get("/records", response_model=list[CostRecordResponse])
async def get_cost_records(
    provider: str | None = None,
    service_type: str | None = None,
    months: int = Query(default=1, ge=1, le=12),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get cost records with optional filtering."""
    service = CostService(db)
    records = await service.get_cost_records(
        int(current_user["id"]),
        provider,
        service_type,
        months,
        limit,
        offset,
    )
    return records


@router.get("/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    months: int = Query(default=1, ge=1, le=12),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get summary of costs over a period."""
    service = CostService(db)
    summary = await service.get_cost_summary(int(current_user["id"]), months)
    return summary


@router.get("/trends", response_model=CostTrendResponse)
async def get_cost_trends(
    months: int = Query(default=6, ge=1, le=24),
    granularity: str = Query(default="monthly", pattern="^(daily|weekly|monthly)$"),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get cost trends over time."""
    service = CostService(db)
    trends = await service.get_cost_trends(int(current_user["id"]), months, granularity)
    return trends


@router.post("/compare", response_model=list[CostComparisonResult])
async def compare_costs(
    request: CostComparisonRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Compare costs against benchmarks."""
    service = CostService(db)
    results = await service.compare_costs(int(current_user["id"]), request)
    return results


@router.get("/savings-opportunities")
async def get_savings_opportunities(
    months: int = Query(default=1, ge=1, le=12),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Find potential savings opportunities."""
    service = CostService(db)
    opportunities = await service.find_savings_opportunities(
        int(current_user["id"]),
        months,
    )
    return {
        'opportunities': opportunities,
        'total_potential_savings': sum(o['potential_savings'] for o in opportunities),
        'count': len(opportunities),
    }


@router.get("/anomalies")
async def detect_anomalies(
    threshold_pct: float = Query(default=50.0, ge=10.0, le=200.0),
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Detect cost anomalies."""
    service = CostService(db)
    anomalies = await service.detect_anomalies(
        int(current_user["id"]),
        threshold_pct,
    )
    return {
        'anomalies': anomalies,
        'count': len(anomalies),
        'threshold_pct': threshold_pct,
    }


# Benchmark management endpoints
@router.post("/benchmarks", response_model=BenchmarkResponse)
async def create_benchmark(
    data: BenchmarkCreateRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Create a new cost benchmark."""
    service = CostService(db)
    benchmark = await service.create_benchmark(int(current_user["id"]), data)
    return benchmark


@router.get("/benchmarks", response_model=list[BenchmarkResponse])
async def list_benchmarks(
    service_type: str | None = None,
    provider: str | None = None,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """List available cost benchmarks."""
    service = CostService(db)
    benchmarks = await service.list_benchmarks(
        int(current_user["id"]),
        service_type,
        provider,
    )
    return benchmarks


@router.delete("/benchmarks/{benchmark_id}")
async def delete_benchmark(
    benchmark_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Delete a cost benchmark."""
    service = CostService(db)
    await service.delete_benchmark(int(current_user["id"]), benchmark_id)
    return {"message": "Benchmark deleted successfully"}
