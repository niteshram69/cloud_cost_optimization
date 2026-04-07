from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    BillingUsageRecord,
    BucketAggregate,
    BucketObjectReference,
    CloudProvider,
    DataTemperature,
)
from backend.app.services.metadata_classifier_service import MetadataFeatures, get_metadata_classifier


@dataclass(slots=True)
class BucketAggregationInput:
    user_id: int
    bucket_id: str
    cloud_provider: CloudProvider
    region: str
    storage_class: str
    resource_name: str
    size_gb: float
    requests_30d: float
    estimated_monthly_cost_usd: float
    latency_ms: float
    storage_record_id: int | None = None
    observed_at: datetime | None = None


class BucketAggregationService:
    OBJECT_REFERENCE_SAMPLE_LIMIT = 100

    def __init__(self, db: Session):
        self.db = db

    def upsert_object_observation(self, payload: BucketAggregationInput) -> BucketAggregate:
        bucket_id = self._normalize_bucket_id(payload.bucket_id, payload.resource_name)
        storage_class = self._normalize_storage_class(payload.storage_class)
        observed_at = payload.observed_at or datetime.now(UTC)

        existing = self.db.scalar(
            select(BucketObjectReference).where(
                BucketObjectReference.user_id == payload.user_id,
                BucketObjectReference.bucket_id == bucket_id,
                BucketObjectReference.cloud_provider == payload.cloud_provider,
                BucketObjectReference.region == payload.region,
                BucketObjectReference.storage_class == storage_class,
                BucketObjectReference.resource_name == payload.resource_name,
            )
        )
        feature_snapshot: dict[str, Any] = {"latency_ms": max(float(payload.latency_ms), 0.0)}
        if existing:
            existing.storage_record_id = payload.storage_record_id
            existing.size_gb = max(float(payload.size_gb), 0.0)
            existing.requests_30d = max(float(payload.requests_30d), 0.0)
            existing.estimated_monthly_cost_usd = max(float(payload.estimated_monthly_cost_usd), 0.0)
            existing.feature_snapshot = feature_snapshot
            existing.last_observed_at = observed_at
        else:
            self.db.add(
                BucketObjectReference(
                    user_id=payload.user_id,
                    storage_record_id=payload.storage_record_id,
                    bucket_id=bucket_id,
                    cloud_provider=payload.cloud_provider,
                    region=payload.region,
                    storage_class=storage_class,
                    resource_name=payload.resource_name,
                    size_gb=max(float(payload.size_gb), 0.0),
                    requests_30d=max(float(payload.requests_30d), 0.0),
                    estimated_monthly_cost_usd=max(float(payload.estimated_monthly_cost_usd), 0.0),
                    feature_snapshot=feature_snapshot,
                    last_observed_at=observed_at,
                )
            )
        self.db.flush()

        return self.refresh_bucket_aggregate(
            user_id=payload.user_id,
            bucket_id=bucket_id,
            cloud_provider=payload.cloud_provider,
            region=payload.region,
            storage_class=storage_class,
        )

    def refresh_bucket_aggregate(
        self,
        *,
        user_id: int,
        bucket_id: str,
        cloud_provider: CloudProvider,
        region: str,
        storage_class: str,
    ) -> BucketAggregate:
        refs = self.db.scalars(
            select(BucketObjectReference).where(
                BucketObjectReference.user_id == user_id,
                BucketObjectReference.bucket_id == bucket_id,
                BucketObjectReference.cloud_provider == cloud_provider,
                BucketObjectReference.region == region,
                BucketObjectReference.storage_class == storage_class,
            )
        ).all()
        if not refs:
            raise ValueError("Bucket aggregate cannot be computed without object references")

        total_objects = len(refs)
        total_size_gb = sum(max(float(ref.size_gb or 0.0), 0.0) for ref in refs)
        total_requests_30d = sum(max(float(ref.requests_30d or 0.0), 0.0) for ref in refs)
        estimated_monthly_cost_usd = sum(max(float(ref.estimated_monthly_cost_usd or 0.0), 0.0) for ref in refs)
        avg_object_size_gb = total_size_gb / total_objects if total_objects > 0 else 0.0
        avg_requests_per_object = total_requests_30d / total_objects if total_objects > 0 else 0.0
        avg_latency_ms = self._average_latency_ms(refs)

        ml = get_metadata_classifier().classify(
            MetadataFeatures(
                requests_30d=float(total_requests_30d),
                latency_ms=float(avg_latency_ms),
                monthly_cost=float(estimated_monthly_cost_usd),
                object_count=float(max(total_objects, 1)),
            )
        )

        observation_days = self._observation_days(refs)
        sorted_refs = sorted(refs, key=lambda item: item.last_observed_at, reverse=True)
        object_references = [item.resource_name for item in sorted_refs[: self.OBJECT_REFERENCE_SAMPLE_LIMIT]]

        aggregate = self.db.scalar(
            select(BucketAggregate).where(
                BucketAggregate.user_id == user_id,
                BucketAggregate.bucket_id == bucket_id,
                BucketAggregate.cloud_provider == cloud_provider,
                BucketAggregate.region == region,
                BucketAggregate.storage_class == storage_class,
            )
        )
        if aggregate is None:
            aggregate = BucketAggregate(
                user_id=user_id,
                bucket_id=bucket_id,
                cloud_provider=cloud_provider,
                region=region,
                storage_class=storage_class,
            )
            self.db.add(aggregate)

        aggregate.total_objects = int(total_objects)
        aggregate.total_size_gb = round(total_size_gb, 6)
        aggregate.avg_object_size_gb = round(avg_object_size_gb, 6)
        aggregate.total_requests_30d = round(total_requests_30d, 6)
        aggregate.avg_requests_per_object = round(avg_requests_per_object, 6)
        aggregate.estimated_monthly_cost_usd = round(estimated_monthly_cost_usd, 6)
        aggregate.temperature = ml.selected
        aggregate.classification_confidence = round(float(ml.ml_confidence), 6)
        aggregate.observation_days = max(int(observation_days), 1)
        aggregate.object_references = object_references

        self._apply_billing_override(bucket=aggregate)
        self.db.flush()
        return aggregate

    def apply_billing_overrides_for_user(
        self,
        *,
        user_id: int,
        provider: CloudProvider | None = None,
        lookback_days: int = 35,
    ) -> int:
        now = datetime.now(UTC)
        lower_bound = now - timedelta(days=max(1, lookback_days))
        query = select(BillingUsageRecord).where(
            BillingUsageRecord.user_id == user_id,
            BillingUsageRecord.usage_end >= lower_bound,
        )
        if provider is not None:
            query = query.where(BillingUsageRecord.provider == provider)
        rows = self.db.scalars(query).all()

        grouped: dict[tuple[str, CloudProvider, str, str], list[BillingUsageRecord]] = {}
        for row in rows:
            bucket_id = self._normalize_bucket_id(row.bucket_id or "", "")
            if not bucket_id:
                continue
            storage_class = self._normalize_storage_class(row.storage_class)
            key = (bucket_id, row.provider, row.region, storage_class)
            grouped.setdefault(key, []).append(row)

        updated = 0
        for (bucket_id, cloud_provider, region, storage_class), group in grouped.items():
            aggregate = self.db.scalar(
                select(BucketAggregate).where(
                    BucketAggregate.user_id == user_id,
                    BucketAggregate.bucket_id == bucket_id,
                    BucketAggregate.cloud_provider == cloud_provider,
                    BucketAggregate.region == region,
                    BucketAggregate.storage_class == storage_class,
                )
            )
            if aggregate is None:
                aggregate = BucketAggregate(
                    user_id=user_id,
                    bucket_id=bucket_id,
                    cloud_provider=cloud_provider,
                    region=region,
                    storage_class=storage_class,
                    temperature=self._dominant_canonical_tier(group),
                    classification_confidence=0.55,
                    object_references=[],
                    total_objects=0,
                    total_size_gb=0.0,
                    avg_object_size_gb=0.0,
                    total_requests_30d=0.0,
                    avg_requests_per_object=0.0,
                    estimated_monthly_cost_usd=0.0,
                    observation_days=1,
                )
                self.db.add(aggregate)

            self._apply_billing_override(bucket=aggregate, rows=group)
            updated += 1

        self.db.flush()
        return updated

    def bucket_for_resource(self, *, user_id: int, resource_name: str) -> BucketAggregate | None:
        ref = self.db.scalar(
            select(BucketObjectReference)
            .where(
                BucketObjectReference.user_id == user_id,
                BucketObjectReference.resource_name == resource_name,
            )
            .order_by(BucketObjectReference.last_observed_at.desc(), BucketObjectReference.id.desc())
        )
        if ref is None:
            return None
        return self.db.scalar(
            select(BucketAggregate).where(
                BucketAggregate.user_id == user_id,
                BucketAggregate.bucket_id == ref.bucket_id,
                BucketAggregate.cloud_provider == ref.cloud_provider,
                BucketAggregate.region == ref.region,
                BucketAggregate.storage_class == ref.storage_class,
            )
        )

    def _apply_billing_override(
        self,
        *,
        bucket: BucketAggregate,
        rows: list[BillingUsageRecord] | None = None,
    ) -> None:
        scoped_rows = rows
        if scoped_rows is None:
            scoped_rows = self.db.scalars(
                select(BillingUsageRecord).where(
                    BillingUsageRecord.user_id == bucket.user_id,
                    BillingUsageRecord.provider == bucket.cloud_provider,
                    BillingUsageRecord.region == bucket.region,
                    BillingUsageRecord.storage_class == bucket.storage_class,
                    BillingUsageRecord.bucket_id == bucket.bucket_id,
                )
            ).all()
        if not scoped_rows:
            return

        total_cost = sum(max(float(row.cost_usd or 0.0), 0.0) for row in scoped_rows)
        usage_quantity = sum(max(float(row.usage_quantity or 0.0), 0.0) for row in scoped_rows)
        window_start = min(row.usage_start for row in scoped_rows)
        window_end = max(row.usage_end for row in scoped_rows)
        window_days = max((window_end.date() - window_start.date()).days + 1, 1)
        monthlyized_cost = (total_cost * 30.0) / window_days

        bucket.actual_monthly_cost_usd = round(monthlyized_cost, 6)
        bucket.usage_quantity = round(usage_quantity, 6)
        bucket.pricing_version = self._latest_pricing_version(scoped_rows)
        bucket.has_real_billing = True
        bucket.observation_days = max(bucket.observation_days, int(window_days))

    def _average_latency_ms(self, rows: list[BucketObjectReference]) -> float:
        latencies: list[float] = []
        for row in rows:
            payload = row.feature_snapshot if isinstance(row.feature_snapshot, dict) else {}
            latency_raw = payload.get("latency_ms")
            try:
                latency = float(latency_raw)
            except (TypeError, ValueError):
                continue
            if latency >= 0:
                latencies.append(latency)
        if not latencies:
            return 320.0
        return sum(latencies) / len(latencies)

    def _observation_days(self, rows: list[BucketObjectReference]) -> int:
        starts = [row.created_at for row in rows]
        ends = [row.last_observed_at for row in rows]
        first_seen = min(starts)
        last_seen = max(ends)
        return max((last_seen.date() - first_seen.date()).days + 1, 1)

    def _latest_pricing_version(self, rows: list[BillingUsageRecord]) -> str | None:
        candidates = [str(row.pricing_version) for row in rows if row.pricing_version]
        if not candidates:
            return None
        return sorted(candidates)[-1]

    def _dominant_canonical_tier(self, rows: list[BillingUsageRecord]) -> DataTemperature:
        by_tier: dict[DataTemperature, float] = {}
        for row in rows:
            by_tier[row.canonical_tier] = by_tier.get(row.canonical_tier, 0.0) + max(float(row.cost_usd or 0.0), 0.0)
        if not by_tier:
            return DataTemperature.COLD
        return max(by_tier.items(), key=lambda item: item[1])[0]

    def _normalize_bucket_id(self, bucket_id: str, resource_name: str) -> str:
        text = str(bucket_id or "").strip()
        if text:
            return text
        fallback = str(resource_name or "").strip()
        return f"resource::{fallback}" if fallback else "resource::unknown"

    def _normalize_storage_class(self, storage_class: str) -> str:
        text = str(storage_class or "").strip()
        if text:
            return text
        return "STANDARD"
