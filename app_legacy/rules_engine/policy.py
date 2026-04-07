"""Policy-driven baseline classifier for storage temperature."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.decision_engine.types import DataTemperature
from app.feature_engineering.models import FeatureVector


@dataclass(slots=True)
class RuleThresholds:
    """Explicit thresholds for deterministic classification."""

    hot_max_last_access_days: int = 7
    hot_min_access_frequency_30d: float = 1.0
    hot_min_read_write_ratio: float = 1.2

    archive_min_last_access_days: int = 180
    archive_max_access_frequency_90d: float = 0.1
    archive_min_object_size_gb: float = 1.0
    archive_max_read_write_ratio: float = 0.6


@dataclass(slots=True)
class RuleClassificationResult:
    """Output of rule-based classification."""

    data_class: DataTemperature
    confidence: float
    reasoning: list[str] = field(default_factory=list)
    rule_scores: dict[str, float] = field(default_factory=dict)


class RuleBasedStorageClassifier:
    """Classifies objects using explicit FinOps/storage lifecycle rules."""

    def __init__(self, thresholds: RuleThresholds | None = None):
        self.thresholds = thresholds or RuleThresholds()

    def classify(self, feature: FeatureVector) -> RuleClassificationResult:
        """Classify object as HOT/COLD/ARCHIVE with transparent reasoning."""
        hot_score = 0.0
        archive_score = 0.0
        reasons: list[str] = []
        t = self.thresholds

        if feature.days_since_last_access <= t.hot_max_last_access_days:
            hot_score += 0.35
            reasons.append(
                f"last access {feature.days_since_last_access:.1f}d <= {t.hot_max_last_access_days}d"
            )
        else:
            archive_score += 0.20
            reasons.append(
                f"last access {feature.days_since_last_access:.1f}d exceeds hot threshold"
            )

        if feature.access_frequency_30d >= t.hot_min_access_frequency_30d:
            hot_score += 0.30
            reasons.append(
                f"30d access frequency {feature.access_frequency_30d:.2f}/day indicates active use"
            )
        else:
            archive_score += 0.25
            reasons.append(
                f"30d access frequency {feature.access_frequency_30d:.2f}/day is low"
            )

        if feature.read_write_ratio >= t.hot_min_read_write_ratio:
            hot_score += 0.15
            reasons.append(
                f"read/write ratio {feature.read_write_ratio:.2f} suggests consumption-heavy workload"
            )
        elif feature.read_write_ratio <= t.archive_max_read_write_ratio:
            archive_score += 0.20
            reasons.append(
                f"read/write ratio {feature.read_write_ratio:.2f} suggests stale or write-once data"
            )

        if feature.days_since_last_access >= t.archive_min_last_access_days:
            archive_score += 0.35
            reasons.append(
                f"last access {feature.days_since_last_access:.1f}d >= {t.archive_min_last_access_days}d"
            )

        if feature.access_frequency_90d <= t.archive_max_access_frequency_90d:
            archive_score += 0.25
            reasons.append(
                f"90d access frequency {feature.access_frequency_90d:.3f}/day <= {t.archive_max_access_frequency_90d}"
            )

        if feature.object_size_gb >= t.archive_min_object_size_gb:
            archive_score += 0.10
            reasons.append(f"object size {feature.object_size_gb:.2f}GB meets archive size baseline")

        if archive_score >= 0.70:
            data_class = DataTemperature.ARCHIVE
            confidence = min(0.98, archive_score)
        elif hot_score >= 0.65 and archive_score < 0.50:
            data_class = DataTemperature.HOT
            confidence = min(0.96, hot_score)
        else:
            data_class = DataTemperature.COLD
            confidence = 0.65 + min(0.25, abs(hot_score - archive_score) / 2)
            reasons.append("object falls between hot and archive bounds")

        return RuleClassificationResult(
            data_class=data_class,
            confidence=round(confidence, 4),
            reasoning=reasons,
            rule_scores={"hot": round(hot_score, 4), "archive": round(archive_score, 4)},
        )
