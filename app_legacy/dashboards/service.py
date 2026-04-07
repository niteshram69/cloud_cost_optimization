"""Dashboard aggregation service for enterprise admin and client views."""

from __future__ import annotations

from collections import Counter, defaultdict

from app.core.monitoring import record_classification_drift
from app.dashboards.schemas import AdminDashboardResponse, ClientDashboardResponse, ProviderSpendItem, RegionComparisonItem
from app.decision_engine.models import OptimizationReport


class DashboardAggregationService:
    """Aggregates optimization reports into admin/client dashboard payloads."""

    def build_admin_dashboard(
        self,
        reports: list[OptimizationReport],
        currency: str,
    ) -> AdminDashboardResponse:
        decisions = [decision for report in reports for decision in report.decisions]

        total_before = sum(item.current_cost["total_monthly_converted"] for item in decisions)
        total_after = sum(item.recommended_cost["total_monthly_converted"] for item in decisions)

        provider_costs: dict[str, float] = defaultdict(float)
        for decision in decisions:
            provider_costs[decision.current_provider] += decision.current_cost["total_monthly_converted"]

        migration_status = Counter(
            (decision.migration or {}).get("status", "not_attempted")
            for decision in decisions
        )
        migration_attempts = sum(count for status, count in migration_status.items() if status != "not_attempted")
        failed_migrations = migration_status.get("failed", 0)
        error_rate = (failed_migrations / migration_attempts) if migration_attempts else 0.0

        ml_confidences = [
            decision.classification.ml_confidence
            for decision in decisions
            if decision.classification.ml_confidence is not None
        ]
        ml_conf_avg = sum(ml_confidences) / len(ml_confidences) if ml_confidences else 0.0

        class_counts = Counter(decision.classification.selected_class.value for decision in decisions)
        class_drift = self._classification_drift_metric(decisions)
        record_classification_drift(class_drift)

        return AdminDashboardResponse(
            currency=currency.upper(),
            total_cloud_spend=round(total_before, 6),
            optimized_spend=round(total_after, 6),
            savings_achieved=round(total_before - total_after, 6),
            migration_status=dict(migration_status),
            error_rate=round(error_rate, 6),
            api_usage={
                "optimization_runs": len(reports),
                "objects_evaluated": len(decisions),
            },
            ml_confidence_avg=round(ml_conf_avg, 6),
            classification_drift=round(class_drift, 6),
            objects_per_class=dict(class_counts),
            provider_spend=[
                ProviderSpendItem(provider=provider, monthly_cost=round(cost, 6))
                for provider, cost in sorted(provider_costs.items(), key=lambda item: item[1], reverse=True)
            ],
        )

    def build_client_dashboard(
        self,
        tenant_id: str,
        reports: list[OptimizationReport],
        currency: str,
    ) -> ClientDashboardResponse:
        decisions = [
            decision
            for report in reports
            for decision in report.decisions
            if decision.tenant_id == tenant_id
        ]

        before = sum(item.current_cost["total_monthly_converted"] for item in decisions)
        after = sum(item.recommended_cost["total_monthly_converted"] for item in decisions)
        monthly_savings = max(0.0, before - after)

        before_by_region: dict[str, float] = defaultdict(float)
        after_by_region: dict[str, float] = defaultdict(float)

        for decision in decisions:
            before_by_region[decision.current_region] += decision.current_cost["total_monthly_converted"]
            after_by_region[decision.recommended_region] += decision.recommended_cost["total_monthly_converted"]

        all_regions = sorted(set(before_by_region) | set(after_by_region))
        region_items = [
            RegionComparisonItem(
                region=region,
                before_cost=round(before_by_region.get(region, 0.0), 6),
                after_cost=round(after_by_region.get(region, 0.0), 6),
            )
            for region in all_regions
        ]

        class_distribution = Counter(decision.classification.selected_class.value for decision in decisions)

        return ClientDashboardResponse(
            tenant_id=tenant_id,
            currency=currency.upper(),
            objects_analyzed=len(decisions),
            monthly_cost_before=round(before, 6),
            monthly_cost_after=round(after, 6),
            monthly_savings=round(monthly_savings, 6),
            yearly_savings=round(monthly_savings * 12, 6),
            region_comparison=region_items,
            class_distribution=dict(class_distribution),
        )

    @staticmethod
    def _classification_drift_metric(decisions: list) -> float:
        if len(decisions) < 20:
            return 0.0

        split = len(decisions) // 2
        baseline = decisions[:split]
        recent = decisions[split:]

        baseline_counts = Counter(item.classification.selected_class.value for item in baseline)
        recent_counts = Counter(item.classification.selected_class.value for item in recent)

        baseline_total = max(1, sum(baseline_counts.values()))
        recent_total = max(1, sum(recent_counts.values()))

        labels = set(baseline_counts) | set(recent_counts)
        distance = 0.0
        for label in labels:
            p = baseline_counts.get(label, 0) / baseline_total
            q = recent_counts.get(label, 0) / recent_total
            distance += abs(p - q)

        # L1/2 bounded between 0 and 1.
        return distance / 2.0
