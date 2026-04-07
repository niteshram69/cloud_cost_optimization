"""Prometheus metrics configuration for API and optimization platform."""

from __future__ import annotations

from collections import Counter as LocalCounter

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info, generate_latest

from app.core.config import settings

# Application info
app_info = Info("costintel_app", "Application information")
app_info.info({
    "version": settings.APP_VERSION,
    "environment": settings.APP_ENVIRONMENT,
})

# Request metrics
request_count = Counter(
    "costintel_requests_total",
    "Total requests",
    ["method", "endpoint", "status"],
)

request_duration = Histogram(
    "costintel_request_duration_seconds",
    "Request duration",
    ["method", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Existing business metrics
ingestion_jobs = Counter(
    "costintel_ingestion_jobs_total",
    "Total ingestion jobs",
    ["status"],
)

classification_jobs = Counter(
    "costintel_classification_jobs_total",
    "Total classification jobs",
    ["status", "category"],
)

webhook_deliveries = Counter(
    "costintel_webhook_deliveries_total",
    "Total webhook deliveries",
    ["status"],
)

# V2 multi-cloud optimization metrics
storage_cost_by_provider_region = Gauge(
    "costintel_storage_cost_usd",
    "Estimated storage monthly cost in USD by provider and region",
    ["provider", "region"],
)

savings_over_time = Counter(
    "costintel_savings_usd_total",
    "Accumulated monthly savings identified by optimizer in USD",
    ["tenant_id"],
)

objects_per_data_class = Gauge(
    "costintel_objects_per_data_class",
    "Objects classified per data class",
    ["data_class"],
)

migration_operations = Counter(
    "costintel_migration_operations_total",
    "Migration outcomes",
    ["status"],
)

ml_confidence_distribution = Histogram(
    "costintel_ml_confidence_score",
    "Distribution of ML classification confidence",
    buckets=[0.0, 0.2, 0.4, 0.6, 0.75, 0.85, 0.95, 1.0],
)

classification_drift_score = Gauge(
    "costintel_classification_drift_score",
    "Drift score between baseline and recent classification distributions",
)

_class_totals: LocalCounter[str] = LocalCounter()


def record_storage_cost(provider: str, region: str, total_monthly_usd: float) -> None:
    """Set latest monthly cost estimate for provider+region."""
    storage_cost_by_provider_region.labels(provider=provider, region=region).set(total_monthly_usd)


def record_savings(tenant_id: str, amount_usd: float) -> None:
    """Increment cumulative savings metric when positive."""
    if amount_usd > 0:
        savings_over_time.labels(tenant_id=tenant_id).inc(amount_usd)


def record_objects_per_data_class(data_class: str) -> None:
    """Update object counts per class."""
    _class_totals[data_class] += 1
    objects_per_data_class.labels(data_class=data_class).set(_class_totals[data_class])


def record_migration_result(status: str) -> None:
    """Increment migration outcome counter."""
    migration_operations.labels(status=status).inc()


def record_ml_confidence(confidence: float) -> None:
    """Observe ML confidence for monitoring quality and fallback behavior."""
    bounded = max(0.0, min(1.0, confidence))
    ml_confidence_distribution.observe(bounded)


def record_classification_drift(score: float) -> None:
    """Set latest classification drift indicator."""
    bounded = max(0.0, min(1.0, score))
    classification_drift_score.set(bounded)


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
