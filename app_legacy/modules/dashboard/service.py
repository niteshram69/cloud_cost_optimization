"""Business logic for dashboard data aggregation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classification.models import ClassificationResult
from app.modules.cost.models import CostRecord
from app.modules.dashboard.schemas import (
    AlertItem,
    CostOverviewChart,
    DashboardAlertsResponse,
    DashboardSummaryResponse,
    IngestionStatusWidget,
    RecommendationsWidget,
    ResourceBreakdownChart,
    TimeSeriesRequest,
    TopResourcesTable,
)
from app.modules.decisions.models import Decision
from app.modules.ingestion.models import IngestionJob


class DashboardService:
    """Service for aggregating dashboard data."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_summary(self, user_id: int) -> DashboardSummaryResponse:
        """Get high-level dashboard summary."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        prev_start = start_date - timedelta(days=30)
        
        # Current month cost
        current_cost = await self._get_total_cost(user_id, start_date, end_date)
        prev_cost = await self._get_total_cost(user_id, prev_start, start_date)
        
        cost_change_pct = 0
        if prev_cost > 0:
            cost_change_pct = float((current_cost - prev_cost) / prev_cost * 100)
        
        # Resource counts
        resource_count = await self._get_resource_count(user_id)
        
        # Classification summary
        classification = await self._get_classification_summary(user_id)
        
        # Pending decisions
        pending = await self._get_pending_decisions(user_id)
        
        # Potential savings
        savings = await self._get_potential_savings(user_id)
        
        # Active providers
        providers = await self._get_active_providers(user_id)
        
        return DashboardSummaryResponse(
            total_monthly_cost=current_cost,
            cost_change_pct=cost_change_pct,
            total_resources=resource_count,
            classification_summary=classification,
            pending_decisions=pending,
            potential_savings=savings,
            active_providers=providers,
        )
    
    async def get_cost_chart(
        self,
        user_id: int,
        months: int = 6,
    ) -> CostOverviewChart:
        """Get cost data formatted for charts."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)
        
        # Get monthly aggregated costs
        result = await self.db.execute(
            select(
                func.date_format(CostRecord.period_start, '%Y-%m').label('month'),
                CostRecord.provider,
                func.sum(CostRecord.cost_amount).label('total')
            )
            .where(
                CostRecord.user_id == user_id,
                CostRecord.period_start >= start_date,
                CostRecord.period_end <= end_date,
            )
            .group_by('month', CostRecord.provider)
            .order_by('month')
        )
        
        rows = result.all()
        
        # Organize by month
        months_data: dict[str, dict[str, Decimal]] = {}
        providers_set: set[str] = set()
        
        for row in rows:
            month = row.month
            provider = row.provider
            total = row.total
            
            if month not in months_data:
                months_data[month] = {}
            months_data[month][provider] = total
            providers_set.add(provider)
        
        # Build chart data
        labels = sorted(months_data.keys())
        datasets = []
        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']
        
        for idx, provider in enumerate(sorted(providers_set)):
            data = [float(months_data.get(m, {}).get(provider, 0)) for m in labels]
            datasets.append({
                'label': provider.upper(),
                'data': data,
                'backgroundColor': colors[idx % len(colors)],
                'borderColor': colors[idx % len(colors)],
            })
        
        return CostOverviewChart(labels=labels, datasets=datasets)
    
    async def get_resource_breakdown(self, user_id: int) -> ResourceBreakdownChart:
        """Get resource breakdown for visualization."""
        from app.modules.metadata.models import MetadataRecord
        
        # By type
        type_result = await self.db.execute(
            select(
                MetadataRecord.entity_type,
                func.count(MetadataRecord.id).label('count')
            )
            .where(MetadataRecord.user_id == user_id)
            .group_by(MetadataRecord.entity_type)
        )
        by_type_rows = type_result.all()
        total = sum(r.count for r in by_type_rows) or 1
        
        by_type = [
            {'type': r.entity_type, 'count': r.count, 'percentage': round(r.count / total * 100, 1)}
            for r in by_type_rows
        ]
        
        # By provider with cost
        provider_result = await self.db.execute(
            select(
                CostRecord.provider,
                func.count(func.distinct(CostRecord.resource_id)).label('count'),
                func.sum(CostRecord.cost_amount).label('cost')
            )
            .where(CostRecord.user_id == user_id)
            .group_by(CostRecord.provider)
        )
        by_provider = [
            {
                'provider': r.provider,
                'count': r.count,
                'cost': float(r.cost) if r.cost else 0,
            }
            for r in provider_result.all()
        ]
        
        # By region with cost
        region_result = await self.db.execute(
            select(
                CostRecord.region,
                func.count(func.distinct(CostRecord.resource_id)).label('count'),
                func.sum(CostRecord.cost_amount).label('cost')
            )
            .where(CostRecord.user_id == user_id)
            .group_by(CostRecord.region)
        )
        by_region = [
            {
                'region': r.region or 'unknown',
                'count': r.count,
                'cost': float(r.cost) if r.cost else 0,
            }
            for r in region_result.all()
        ]
        
        return ResourceBreakdownChart(by_type=by_type, by_provider=by_provider, by_region=by_region)
    
    async def get_top_resources(
        self,
        user_id: int,
        limit: int = 10,
    ) -> list[TopResourcesTable]:
        """Get top resources by cost."""
        # Current month
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        result = await self.db.execute(
            select(
                CostRecord.resource_id,
                CostRecord.service_type,
                CostRecord.provider,
                func.sum(CostRecord.cost_amount).label('cost')
            )
            .where(
                CostRecord.user_id == user_id,
                CostRecord.period_start >= start_date,
            )
            .group_by(CostRecord.resource_id, CostRecord.service_type, CostRecord.provider)
            .order_by(func.sum(CostRecord.cost_amount).desc())
            .limit(limit)
        )
        
        resources = []
        for row in result.all():
            # Simple trend calculation (compare to previous month)
            trend = 'stable'
            trend_pct = 0.0
            
            resources.append(TopResourcesTable(
                resource_id=row.resource_id,
                service_type=row.service_type,
                provider=row.provider,
                monthly_cost=row.cost,
                trend=trend,
                trend_pct=trend_pct,
            ))
        
        return resources
    
    async def get_recommendations_widget(self, user_id: int) -> RecommendationsWidget:
        """Get recommendations summary for dashboard widget."""
        # Pending decisions by priority (based on potential savings)
        result = await self.db.execute(
            select(Decision)
            .where(
                Decision.user_id == user_id,
                Decision.approved_at == None,
                Decision.dismissed_at == None,
            )
            .order_by(Decision.estimated_savings_monthly.desc())
        )
        
        decisions = result.scalars().all()
        
        # Categorize by priority
        high_priority = [d for d in decisions if d.estimated_savings_monthly and d.estimated_savings_monthly > 100]
        medium_priority = [d for d in decisions if d.estimated_savings_monthly and 20 < d.estimated_savings_monthly <= 100]
        low_priority = [d for d in decisions if d.estimated_savings_monthly and d.estimated_savings_monthly <= 20]
        
        total_savings = sum(d.estimated_savings_monthly or 0 for d in decisions)
        
        by_priority = [
            {'priority': 'high', 'count': len(high_priority), 'potential_savings': float(sum(d.estimated_savings_monthly or 0 for d in high_priority))},
            {'priority': 'medium', 'count': len(medium_priority), 'potential_savings': float(sum(d.estimated_savings_monthly or 0 for d in medium_priority))},
            {'priority': 'low', 'count': len(low_priority), 'potential_savings': float(sum(d.estimated_savings_monthly or 0 for d in low_priority))},
        ]
        
        # Top actions
        top_actions = [
            {
                'action': d.action_type,
                'resource_id': d.context.get('resource_id', 'unknown') if d.context else 'unknown',
                'savings': float(d.estimated_savings_monthly) if d.estimated_savings_monthly else 0,
            }
            for d in decisions[:5]
        ]
        
        return RecommendationsWidget(
            total_recommendations=len(decisions),
            by_priority=by_priority,
            top_actions=top_actions,
        )
    
    async def get_ingestion_status(self, user_id: int) -> IngestionStatusWidget:
        """Get recent ingestion job status."""
        # Recent jobs
        result = await self.db.execute(
            select(IngestionJob)
            .where(IngestionJob.user_id == user_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(5)
        )
        
        recent = result.scalars().all()
        recent_jobs = [
            {
                'id': j.id,
                'status': j.status,
                'file_name': j.file_name,
                'records_processed': j.job_metadata.get('records_extracted', 0) if j.job_metadata else 0,
            }
            for j in recent
        ]
        
        # Jobs today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        jobs_today_result = await self.db.execute(
            select(func.count(IngestionJob.id))
            .where(
                IngestionJob.user_id == user_id,
                IngestionJob.created_at >= today_start,
            )
        )
        jobs_today = jobs_today_result.scalar() or 0
        
        # Jobs this week
        week_start = today_start - timedelta(days=today_start.weekday())
        jobs_week_result = await self.db.execute(
            select(func.count(IngestionJob.id))
            .where(
                IngestionJob.user_id == user_id,
                IngestionJob.created_at >= week_start,
            )
        )
        jobs_week = jobs_week_result.scalar() or 0
        
        # Total records
        total_records_result = await self.db.execute(
            select(func.sum(IngestionJob.file_size))
            .where(IngestionJob.user_id == user_id)
        )
        total_records = total_records_result.scalar() or 0
        
        return IngestionStatusWidget(
            recent_jobs=recent_jobs,
            jobs_today=jobs_today,
            jobs_this_week=jobs_week,
            total_records=int(total_records),
        )
    
    async def get_alerts(self, user_id: int) -> DashboardAlertsResponse:
        """Get active alerts for the dashboard."""
        alerts: list[AlertItem] = []
        
        # Check for high cost anomalies
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        
        high_cost_result = await self.db.execute(
            select(CostRecord)
            .where(
                CostRecord.user_id == user_id,
                CostRecord.period_start >= start_date,
                CostRecord.cost_amount > 1000,
            )
            .order_by(CostRecord.cost_amount.desc())
            .limit(1)
        )
        
        high_cost = high_cost_result.scalar_one_or_none()
        if high_cost:
            alerts.append(AlertItem(
                severity='warning',
                message=f"High cost detected: {high_cost.resource_id} (${float(high_cost.cost_amount):.2f})",
                resource_id=high_cost.resource_id,
                action_url=f"/api/v1/cost/records/{high_cost.id}",
                detected_at=high_cost.created_at,
            ))
        
        # Check for failed ingestion jobs
        failed_result = await self.db.execute(
            select(IngestionJob)
            .where(
                IngestionJob.user_id == user_id,
                IngestionJob.status == 'failed',
            )
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        
        failed = failed_result.scalar_one_or_none()
        if failed:
            alerts.append(AlertItem(
                severity='info',
                message=f"Recent ingestion job failed: {failed.file_name}",
                resource_id=None,
                action_url=f"/api/v1/ingestion/jobs/{failed.id}",
                detected_at=failed.created_at,
            ))
        
        critical_count = sum(1 for a in alerts if a.severity == 'critical')
        warning_count = sum(1 for a in alerts if a.severity == 'warning')
        
        return DashboardAlertsResponse(
            alerts=alerts,
            total_count=len(alerts),
            critical_count=critical_count,
            warning_count=warning_count,
        )
    
    # === Helper methods ===
    
    async def _get_total_cost(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        """Get total cost for a period."""
        result = await self.db.execute(
            select(func.sum(CostRecord.cost_amount))
            .where(
                CostRecord.user_id == user_id,
                CostRecord.period_start >= start,
                CostRecord.period_end <= end,
            )
        )
        return result.scalar() or Decimal('0')
    
    async def _get_resource_count(self, user_id: int) -> int:
        """Get total resource count."""
        from app.modules.metadata.models import MetadataRecord
        
        result = await self.db.execute(
            select(func.count(MetadataRecord.id))
            .where(MetadataRecord.user_id == user_id)
        )
        return result.scalar() or 0
    
    async def _get_classification_summary(self, user_id: int) -> dict[str, int]:
        """Get classification summary."""
        result = await self.db.execute(
            select(
                ClassificationResult.category,
                func.count(ClassificationResult.id).label('count')
            )
            .where(ClassificationResult.user_id == user_id)
            .group_by(ClassificationResult.category)
        )
        return {row.category: row.count for row in result.all()}
    
    async def _get_pending_decisions(self, user_id: int) -> int:
        """Get count of pending decisions."""
        result = await self.db.execute(
            select(func.count(Decision.id))
            .where(
                Decision.user_id == user_id,
                Decision.approved_at == None,
                Decision.dismissed_at == None,
            )
        )
        return result.scalar() or 0
    
    async def _get_potential_savings(self, user_id: int) -> Decimal:
        """Get total potential savings."""
        result = await self.db.execute(
            select(func.sum(Decision.estimated_savings_monthly))
            .where(
                Decision.user_id == user_id,
                Decision.dismissed_at == None,
            )
        )
        return result.scalar() or Decimal('0')
    
    async def _get_active_providers(self, user_id: int) -> list[str]:
        """Get list of active providers."""
        result = await self.db.execute(
            select(CostRecord.provider)
            .where(CostRecord.user_id == user_id)
            .distinct()
        )
        return [row.provider for row in result.all()]
