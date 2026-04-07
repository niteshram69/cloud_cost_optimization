"""Decision-layer models for optimization outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.decision_engine.types import DataTemperature, DecisionAction, DecisionMode


@dataclass(slots=True)
class ClassificationOutcome:
    """Final class selection including fallback details."""

    selected_class: DataTemperature
    source: str
    confidence: float
    rule_confidence: float
    ml_confidence: float | None
    fallback_used: bool
    reasoning: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["selected_class"] = self.selected_class.value
        return payload


@dataclass(slots=True)
class ObjectOptimizationDecision:
    """Actionable recommendation for one object or dataset."""

    tenant_id: str
    object_id: str
    current_provider: str
    current_region: str
    current_tier: str
    recommended_provider: str
    recommended_region: str
    recommended_tier: str
    mode: DecisionMode
    action: DecisionAction
    classification: ClassificationOutcome
    current_cost: dict
    recommended_cost: dict
    alternatives: list[dict]
    estimated_monthly_savings: float
    estimated_yearly_savings: float
    explanation: str
    migration: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["action"] = self.action.value
        payload["classification"] = self.classification.to_dict()
        return payload


@dataclass(slots=True)
class OptimizationReport:
    """Batch optimization report."""

    decisions: list[ObjectOptimizationDecision]
    currency: str
    mode: DecisionMode

    @property
    def total_current_monthly_cost(self) -> float:
        return round(sum(item.current_cost["total_monthly_converted"] for item in self.decisions), 6)

    @property
    def total_recommended_monthly_cost(self) -> float:
        return round(sum(item.recommended_cost["total_monthly_converted"] for item in self.decisions), 6)

    @property
    def total_monthly_savings(self) -> float:
        return round(sum(item.estimated_monthly_savings for item in self.decisions), 6)

    @property
    def total_yearly_savings(self) -> float:
        return round(sum(item.estimated_yearly_savings for item in self.decisions), 6)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "currency": self.currency.upper(),
            "summary": {
                "objects_evaluated": len(self.decisions),
                "total_current_monthly_cost": self.total_current_monthly_cost,
                "total_recommended_monthly_cost": self.total_recommended_monthly_cost,
                "total_monthly_savings": self.total_monthly_savings,
                "total_yearly_savings": self.total_yearly_savings,
            },
            "decisions": [item.to_dict() for item in self.decisions],
        }
