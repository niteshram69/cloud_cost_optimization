from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["HOT", "COLD", "ARCHIVE"]


@dataclass(slots=True)
class ConfidenceInputs:
    ml_probability: float
    predicted_tier: Tier
    days_since_last_access: float
    access_frequency_30d: float
    object_size_gb: float
    historical_volatility: float
    pricing_delta_ratio: float


@dataclass(slots=True)
class ConfidenceResult:
    confidence_score: float
    rule_agreement: float
    cost_signal_strength: float
    action_band: Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(slots=True)
class ConfidenceDecayInputs:
    confidence_base: float
    object_count: int
    total_size_gb: float
    observation_days: int
    pricing_confidence: Literal["REAL", "EXPORT", "ESTIMATE"]
    optimization_unit: Literal["BUCKET", "OBJECT"]
    is_cross_cloud_move: bool
    access_count_30d: float


@dataclass(slots=True)
class ConfidenceDecayResult:
    confidence_base: float
    data_window_factor: float
    billing_realism_factor: float
    aggregation_factor: float
    migration_risk_factor: float
    confidence_final: float
    policy_action: Literal["MOVE_TO_PREDICTED_TIER", "MOVE_TO_STANDARD_IA", "RETAIN"]
    policy_band: Literal["HIGH", "MEDIUM", "LOW"]
    downgrade_reasons: list[str]


def compute_confidence_score(inputs: ConfidenceInputs) -> ConfidenceResult:
    """
    FinOps-auditable confidence scoring.

    Final confidence combines:
      - 60% ML probability
      - 25% rule agreement
      - 15% cost signal strength

    Formula:
      final_confidence =
        0.6 * ml_probability +
        0.25 * rule_agreement +
        0.15 * cost_signal_strength

    Action bands:
      - HIGH:   > 0.85  (cross-cloud move allowed)
      - MEDIUM: 0.60-0.85 (same-cloud downgrade only)
      - LOW:    < 0.60 (advisory only)
    """
    ml_probability = _clamp(inputs.ml_probability)
    rule_agreement = _rule_agreement_score(
        predicted_tier=inputs.predicted_tier,
        days_since_last_access=inputs.days_since_last_access,
        access_frequency_30d=inputs.access_frequency_30d,
        object_size_gb=inputs.object_size_gb,
        historical_volatility=inputs.historical_volatility,
    )
    cost_signal_strength = _cost_signal_strength(inputs.pricing_delta_ratio)

    confidence = (
        0.6 * ml_probability
        + 0.25 * rule_agreement
        + 0.15 * cost_signal_strength
    )
    confidence = _clamp(confidence)

    if confidence > 0.85:
        action_band: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    elif confidence >= 0.60:
        action_band = "MEDIUM"
    else:
        action_band = "LOW"

    return ConfidenceResult(
        confidence_score=round(confidence, 6),
        rule_agreement=round(rule_agreement, 6),
        cost_signal_strength=round(cost_signal_strength, 6),
        action_band=action_band,
    )


def _rule_agreement_score(
    *,
    predicted_tier: Tier,
    days_since_last_access: float,
    access_frequency_30d: float,
    object_size_gb: float,
    historical_volatility: float,
) -> float:
    """
    Deterministic agreement signal in [0, 1].

    Rules are intentionally interpretable for enterprise audits.
    Each rule votes if it supports the ML-predicted tier.
    """
    votes_total = 5
    votes_match = 0

    # Rule 1: recency
    if days_since_last_access <= 7 and predicted_tier == "HOT":
        votes_match += 1
    elif 8 <= days_since_last_access <= 90 and predicted_tier == "COLD":
        votes_match += 1
    elif days_since_last_access > 90 and predicted_tier == "ARCHIVE":
        votes_match += 1

    # Rule 2: access frequency
    if access_frequency_30d >= 1000 and predicted_tier == "HOT":
        votes_match += 1
    elif 50 <= access_frequency_30d < 1000 and predicted_tier == "COLD":
        votes_match += 1
    elif access_frequency_30d < 50 and predicted_tier == "ARCHIVE":
        votes_match += 1

    # Rule 3: volatility
    if historical_volatility >= 0.6 and predicted_tier == "HOT":
        votes_match += 1
    elif 0.25 <= historical_volatility < 0.6 and predicted_tier == "COLD":
        votes_match += 1
    elif historical_volatility < 0.25 and predicted_tier == "ARCHIVE":
        votes_match += 1

    # Rule 4: object size bias
    if object_size_gb < 10 and predicted_tier == "HOT":
        votes_match += 1
    elif 10 <= object_size_gb < 500 and predicted_tier == "COLD":
        votes_match += 1
    elif object_size_gb >= 500 and predicted_tier == "ARCHIVE":
        votes_match += 1

    # Rule 5: hot safety rule
    # Recently active data should not be archived aggressively.
    if days_since_last_access <= 30 and predicted_tier != "ARCHIVE":
        votes_match += 1
    elif days_since_last_access > 30:
        votes_match += 1

    return _clamp(votes_match / votes_total)


def _cost_signal_strength(pricing_delta_ratio: float) -> float:
    """
    Normalize savings ratio into [0, 1].

    pricing_delta_ratio = (current_cost - optimized_cost) / max(current_cost, epsilon)
    """
    return _clamp(pricing_delta_ratio)


def _clamp(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return float(value)


def apply_confidence_decay(inputs: ConfidenceDecayInputs) -> ConfidenceDecayResult:
    """
    Formal multiplicative confidence decay model.

    Derivation:
      confidence_final =
        confidence_base
        * data_window_factor
        * billing_realism_factor
        * aggregation_factor
        * migration_risk_factor

    Worked example:
      base=0.99, data_window=0.8, billing_realism=0.75,
      aggregation=1.0, migration_risk=1.0
      -> confidence_final = 0.99 * 0.8 * 0.75 * 1.0 * 1.0 = 0.594

    Policy bands:
      - HIGH (> 0.80): MOVE_TO_PREDICTED_TIER
      - MEDIUM (0.50-0.80): MOVE_TO_STANDARD_IA
      - LOW (< 0.50): RETAIN
    """
    confidence_base = _clamp(inputs.confidence_base)
    data_window_factor = _data_window_factor(observation_days=max(inputs.observation_days, 0))
    billing_realism_factor = _billing_realism_factor(pricing_confidence=inputs.pricing_confidence)
    aggregation_factor = _aggregation_factor(
        optimization_unit=inputs.optimization_unit,
        object_count=max(inputs.object_count, 0),
    )
    migration_risk_factor = _migration_risk_factor(
        is_cross_cloud_move=inputs.is_cross_cloud_move,
        access_count_30d=max(inputs.access_count_30d, 0.0),
    )

    confidence_final = _clamp(
        confidence_base
        * data_window_factor
        * billing_realism_factor
        * aggregation_factor
        * migration_risk_factor
    )
    downgrade_reasons: list[str] = []
    if data_window_factor < 1.0:
        downgrade_reasons.append(f"Limited observation window ({inputs.observation_days} days).")
    if billing_realism_factor < 1.0:
        downgrade_reasons.append(
            f"Pricing realism '{inputs.pricing_confidence}' reduced confidence."
        )
    if aggregation_factor < 1.0:
        downgrade_reasons.append(
            f"Object-level aggregation penalty ({inputs.object_count} objects, {inputs.total_size_gb:.2f} GB)."
        )
    if migration_risk_factor < 1.0:
        cross_cloud_text = "cross-cloud" if inputs.is_cross_cloud_move else "same-cloud"
        downgrade_reasons.append(
            f"Migration risk penalty ({cross_cloud_text}, access={inputs.access_count_30d:.0f}/30d)."
        )

    if confidence_final > 0.80:
        policy_action: Literal["MOVE_TO_PREDICTED_TIER", "MOVE_TO_STANDARD_IA", "RETAIN"] = "MOVE_TO_PREDICTED_TIER"
        policy_band: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    elif confidence_final >= 0.50:
        policy_action = "MOVE_TO_STANDARD_IA"
        policy_band = "MEDIUM"
    else:
        policy_action = "RETAIN"
        policy_band = "LOW"

    return ConfidenceDecayResult(
        confidence_base=round(confidence_base, 6),
        data_window_factor=round(data_window_factor, 6),
        billing_realism_factor=round(billing_realism_factor, 6),
        aggregation_factor=round(aggregation_factor, 6),
        migration_risk_factor=round(migration_risk_factor, 6),
        confidence_final=round(confidence_final, 6),
        policy_action=policy_action,
        policy_band=policy_band,
        downgrade_reasons=downgrade_reasons,
    )


def _data_window_factor(*, observation_days: int) -> float:
    if observation_days > 90:
        return 1.0
    if observation_days >= 30:
        return 0.8
    return 0.6


def _billing_realism_factor(*, pricing_confidence: Literal["REAL", "EXPORT", "ESTIMATE"]) -> float:
    if pricing_confidence == "REAL":
        return 1.0
    if pricing_confidence == "EXPORT":
        return 0.9
    return 0.75


def _aggregation_factor(*, optimization_unit: Literal["BUCKET", "OBJECT"], object_count: int) -> float:
    if optimization_unit == "BUCKET":
        return 1.0
    if object_count >= 1000:
        return 0.9
    return 0.85


def _migration_risk_factor(*, is_cross_cloud_move: bool, access_count_30d: float) -> float:
    if not is_cross_cloud_move:
        if access_count_30d > 20_000:
            return 0.9
        return 1.0
    if access_count_30d > 10:
        return 0.72
    return 0.82
