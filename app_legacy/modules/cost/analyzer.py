"""Cost analysis and benchmarking logic."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.modules.cost.models import Benchmark, CostRecord


class CostAnalyzer:
    """Analyzes costs and compares against benchmarks."""
    
    def __init__(self):
        pass
    
    def calculate_unit_cost(
        self,
        cost_amount: Decimal,
        usage_quantity: Decimal,
    ) -> Decimal:
        """Calculate cost per unit."""
        if usage_quantity and usage_quantity > 0:
            return cost_amount / usage_quantity
        return Decimal('0')
    
    def compare_to_benchmark(
        self,
        cost_record: CostRecord,
        benchmark: Benchmark | None,
    ) -> dict:
        """
        Compare a cost record against a benchmark.
        
        Returns comparison result with variance and potential savings.
        """
        if not benchmark:
            return {
                'comparison_status': 'no_benchmark',
                'variance_pct': None,
                'potential_savings': None,
                'benchmark_avg': None,
                'benchmark_min': None,
                'benchmark_max': None,
            }
        
        current_unit_cost = self.calculate_unit_cost(
            cost_record.cost_amount,
            cost_record.usage_quantity
        )
        
        variance_pct = None
        potential_savings = None
        
        if benchmark.avg_cost_per_unit and benchmark.avg_cost_per_unit > 0:
            variance_pct = (
                (current_unit_cost - benchmark.avg_cost_per_unit) 
                / benchmark.avg_cost_per_unit * 100
            )
            
            # Calculate potential savings if above average
            if current_unit_cost > benchmark.avg_cost_per_unit:
                potential_savings = (
                    current_unit_cost - benchmark.avg_cost_per_unit
                ) * cost_record.usage_quantity
        
        # Determine status
        if benchmark.avg_cost_per_unit:
            if current_unit_cost <= benchmark.avg_cost_per_unit:
                status = 'optimal'
            elif current_unit_cost <= benchmark.avg_cost_per_unit * Decimal('1.2'):
                status = 'above_average'
            else:
                status = 'high'
        else:
            status = 'no_benchmark'
        
        return {
            'comparison_status': status,
            'variance_pct': variance_pct,
            'potential_savings': potential_savings,
            'benchmark_avg': benchmark.avg_cost_per_unit,
            'benchmark_min': benchmark.min_cost_per_unit,
            'benchmark_max': benchmark.max_cost_per_unit,
        }
    
    def detect_anomalies(
        self,
        cost_records: list[CostRecord],
        threshold_pct: Decimal = Decimal('50'),
    ) -> list[dict]:
        """
        Detect cost anomalies based on statistical analysis.
        
        Simple implementation: flags costs that are X% higher than average
        for the same service type.
        """
        if not cost_records:
            return []
        
        # Group by service type
        by_service: dict[str, list[CostRecord]] = {}
        for record in cost_records:
            service = record.service_type
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(record)
        
        anomalies = []
        
        for service, records in by_service.items():
            if len(records) < 2:
                continue
            
            # Calculate average unit cost for this service
            unit_costs = [
                self.calculate_unit_cost(r.cost_amount, r.usage_quantity)
                for r in records
            ]
            avg_cost = sum(unit_costs) / len(unit_costs)
            
            if avg_cost == 0:
                continue
            
            # Check for outliers
            for record in records:
                unit_cost = self.calculate_unit_cost(
                    record.cost_amount,
                    record.usage_quantity
                )
                
                if unit_cost > avg_cost * (1 + threshold_pct / 100):
                    variance_pct = ((unit_cost - avg_cost) / avg_cost) * 100
                    
                    # Determine severity
                    if variance_pct > 100:
                        severity = 'high'
                    elif variance_pct > 75:
                        severity = 'medium'
                    else:
                        severity = 'low'
                    
                    anomalies.append({
                        'resource_id': record.resource_id,
                        'service_type': record.service_type,
                        'detected_at': datetime.now(timezone.utc),
                        'expected_cost': avg_cost * record.usage_quantity,
                        'actual_cost': record.cost_amount,
                        'variance_pct': variance_pct,
                        'severity': severity,
                    })
        
        return anomalies
    
    def calculate_trends(
        self,
        cost_records: list[CostRecord],
        granularity: str = 'monthly',
    ) -> list[dict]:
        """
        Calculate cost trends over time.
        
        Args:
            cost_records: List of cost records
            granularity: 'daily', 'weekly', 'monthly'
        """
        if not cost_records:
            return []
        
        # Group by period
        periods: dict[str, list[CostRecord]] = {}
        
        for record in cost_records:
            if granularity == 'daily':
                period_key = record.period_start.strftime('%Y-%m-%d')
            elif granularity == 'weekly':
                period_key = record.period_start.strftime('%Y-W%U')
            else:  # monthly
                period_key = record.period_start.strftime('%Y-%m')
            
            if period_key not in periods:
                periods[period_key] = []
            periods[period_key].append(record)
        
        # Calculate summary for each period
        trends = []
        for period_key in sorted(periods.keys()):
            records = periods[period_key]
            
            total_cost = sum(r.cost_amount for r in records)
            
            by_provider: dict[str, Decimal] = {}
            by_service: dict[str, Decimal] = {}
            
            for r in records:
                by_provider[r.provider] = by_provider.get(r.provider, Decimal('0')) + r.cost_amount
                by_service[r.service_type] = by_service.get(r.service_type, Decimal('0')) + r.cost_amount
            
            trends.append({
                'period': period_key,
                'total_cost': total_cost,
                'record_count': len(records),
                'by_provider': {k: float(v) for k, v in by_provider.items()},
                'by_service': {k: float(v) for k, v in by_service.items()},
            })
        
        return trends
    
    def find_savings_opportunities(
        self,
        cost_records: list[CostRecord],
        benchmarks: list[Benchmark],
    ) -> list[dict]:
        """
        Identify potential savings opportunities.
        
        Compares costs against benchmarks and identifies over-provisioned
        or underutilized resources.
        """
        opportunities = []
        
        # Create lookup for benchmarks
        benchmark_lookup: dict[tuple, Benchmark] = {}
        for b in benchmarks:
            key = (b.service_type, b.provider, b.region)
            benchmark_lookup[key] = b
        
        for record in cost_records:
            # Find matching benchmark
            key = (record.service_type, record.provider, record.region)
            benchmark = benchmark_lookup.get(key)
            
            if not benchmark:
                continue
            
            comparison = self.compare_to_benchmark(record, benchmark)
            
            if comparison['potential_savings'] and comparison['potential_savings'] > 0:
                opportunities.append({
                    'resource_id': record.resource_id,
                    'service_type': record.service_type,
                    'current_monthly_cost': record.cost_amount,
                    'potential_savings': comparison['potential_savings'],
                    'savings_pct': comparison['variance_pct'],
                    'recommendation': self._generate_recommendation(
                        record.service_type,
                        comparison['comparison_status']
                    ),
                })
        
        # Sort by potential savings (highest first)
        opportunities.sort(key=lambda x: x['potential_savings'], reverse=True)
        
        return opportunities
    
    def _generate_recommendation(self, service_type: str, status: str) -> str:
        """Generate a recommendation based on service type and status."""
        recommendations = {
            'compute_instance': {
                'high': 'Consider downsizing instance or using reserved instances',
                'above_average': 'Review utilization patterns for optimization',
            },
            'storage_bucket': {
                'high': 'Move infrequently accessed data to cheaper storage tier',
                'above_average': 'Review storage lifecycle policies',
            },
            'database': {
                'high': 'Consider reserved capacity or smaller instance class',
                'above_average': 'Review database utilization and indexing',
            },
        }
        
        service_rec = recommendations.get(service_type, {})
        return service_rec.get(status, 'Review resource for optimization opportunities')
