"""Feature engineering models for rule-based and ML classifiers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class FeatureVector:
    """Unified feature vector for a single object."""

    tenant_id: str
    object_id: str
    provider: str
    region: str
    bucket: str
    current_tier: str
    object_size_gb: float
    days_since_last_access: float
    access_frequency_30d: float
    access_frequency_90d: float
    read_write_ratio: float
    storage_growth_trend_gb_30d: float
    access_pattern_entropy: float
    read_count_30d: int
    write_count_30d: int
    read_count_90d: int
    write_count_90d: int

    def ml_columns(self) -> list[float]:
        """Feature order used by the ML model."""
        return [
            self.days_since_last_access,
            self.access_frequency_30d,
            self.access_frequency_90d,
            self.object_size_gb,
            self.storage_growth_trend_gb_30d,
            self.access_pattern_entropy,
            self.read_write_ratio,
        ]

    def to_dict(self) -> dict:
        """Dict representation for APIs/audits."""
        return asdict(self)
