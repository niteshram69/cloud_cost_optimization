"""Transforms metadata/access snapshots into classifier-ready features."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from app.collectors.models import ObjectUsageSnapshot
from app.feature_engineering.models import FeatureVector

BYTES_PER_GB = 1024**3


class FeatureEngineeringService:
    """Generates deterministic features for rules and ML models."""

    def build_feature(
        self,
        snapshot: ObjectUsageSnapshot,
        as_of: datetime | None = None,
    ) -> FeatureVector:
        """Build a single feature vector from a usage snapshot."""
        as_of = as_of or datetime.now(UTC)

        last_access = (
            snapshot.access.last_read_at
            or snapshot.access.last_write_at
            or snapshot.inventory.last_accessed_at
            or snapshot.inventory.last_modified_at
        )

        days_since_last_access = max(0.0, (as_of - last_access).total_seconds() / 86400)
        size_gb = max(0.0, snapshot.inventory.size_bytes / BYTES_PER_GB)

        read_30d = snapshot.access.read_count_30d
        write_30d = snapshot.access.write_count_30d
        read_90d = snapshot.access.read_count_90d
        write_90d = snapshot.access.write_count_90d

        access_frequency_30d = (read_30d + write_30d) / 30.0
        access_frequency_90d = (read_90d + write_90d) / 90.0

        growth_bytes_90d = int(snapshot.inventory.metadata.get("growth_bytes_90d", "0"))
        growth_trend_gb_30d = (growth_bytes_90d / BYTES_PER_GB) / 3.0

        entropy = self._entropy(snapshot.access.daily_reads_30d, snapshot.access.daily_writes_30d)

        return FeatureVector(
            tenant_id=snapshot.tenant_id,
            object_id=snapshot.object_id,
            provider=snapshot.inventory.provider,
            region=snapshot.inventory.region,
            bucket=snapshot.inventory.bucket,
            current_tier=snapshot.inventory.storage_tier,
            object_size_gb=size_gb,
            days_since_last_access=days_since_last_access,
            access_frequency_30d=access_frequency_30d,
            access_frequency_90d=access_frequency_90d,
            read_write_ratio=snapshot.access.read_write_ratio,
            storage_growth_trend_gb_30d=growth_trend_gb_30d,
            access_pattern_entropy=entropy,
            read_count_30d=read_30d,
            write_count_30d=write_30d,
            read_count_90d=read_90d,
            write_count_90d=write_90d,
        )

    def build_features(
        self,
        snapshots: list[ObjectUsageSnapshot],
        as_of: datetime | None = None,
    ) -> list[FeatureVector]:
        """Build feature vectors for a collection of snapshots."""
        return [self.build_feature(snapshot, as_of=as_of) for snapshot in snapshots]

    @staticmethod
    def _entropy(reads: list[int], writes: list[int]) -> float:
        series = [max(0, r) + max(0, w) for r, w in zip(reads, writes, strict=False)]
        total = sum(series)
        if total <= 0:
            return 0.0

        probabilities = [value / total for value in series if value > 0]
        return -sum(prob * math.log2(prob) for prob in probabilities)
