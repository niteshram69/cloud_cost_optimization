from __future__ import annotations

from dataclasses import dataclass
import math

from backend.app.schemas.ingest import OptimizerDecisionSchema, ResourceIngestItem

BYTES_IN_GB = 1024.0 * 1024.0 * 1024.0
LARGE_OBJECT_TB = 5.0
ARCHIVE_REQUESTS_THRESHOLD = 200
RETRIEVAL_PENALTY_MAX = 200.0
TEMPERATURE_RAW_MAX = 3.0
RISK_THRESHOLD = 0.5
RISK_HIGH_THRESHOLD = 0.6
MIN_CONFIDENCE_FOR_MIGRATION = 0.6
VOLATILITY_UNSTABLE_THRESHOLD = 0.8


@dataclass(slots=True)
class Prediction:
    provider: str
    storage_tier: str
    classification: str


class OptimizerService:
    """
    FinOps decision engine for a single resource.

    The service is deterministic, explainable, and side-effect free.
    """

    def optimize(self, resource: ResourceIngestItem) -> OptimizerDecisionSchema:
        trace: list[str] = []

        object_size_gb = max(float(resource.object_size_bytes) / BYTES_IN_GB, 0.0)
        access_frequency = float(resource.requests_30d) / 30.0
        recency_score = math.exp(-float(resource.last_access_days) / 30.0)
        effective_access = float(resource.requests_30d) * math.exp(-float(resource.last_access_days) / 30.0)
        access_volatility = float(resource.access_std_dev) / (float(resource.requests_30d) + 1.0)
        read_write_ratio = max(0.1, min(10.0, float(resource.read_write_ratio)))
        momentum_denominator = max(float(resource.requests_90d) / 3.0, 1e-6)
        momentum = float(resource.requests_30d) / momentum_denominator
        momentum = max(0.2, min(2.0, momentum))
        current_storage_cost = float(resource.estimated_monthly_cost_usd)
        if current_storage_cost <= 0 and resource.storage_cost_per_gb is not None:
            current_storage_cost = object_size_gb * float(resource.storage_cost_per_gb)

        retrieval_penalty_source = "estimated_monthly_cost_usd"
        if resource.retrieval_cost_per_gb is not None and resource.retrieval_cost_per_gb > 0:
            retrieval_penalty = object_size_gb * float(resource.retrieval_cost_per_gb)
            retrieval_penalty_source = "retrieval_cost_per_gb"
        else:
            size_factor = max(object_size_gb / 1024.0, 1.0)
            retrieval_penalty = float(resource.estimated_monthly_cost_usd) * size_factor

        temperature_raw = (
            0.40 * math.log10(float(resource.requests_30d) + 1.0)
            + 0.25 * recency_score
            + 0.15 * read_write_ratio
            + 0.10 * momentum
            - 0.10 * access_volatility
        )
        temperature_score = self._normalize_temperature(temperature_raw)
        temperature_classification = self._classify_temperature(temperature_score=temperature_score)
        classification = temperature_classification
        trace.append(
            f"Temperature score={temperature_score:.2f} from raw={temperature_raw:.3f} "
            f"(freq={access_frequency:.2f}/day recency={recency_score:.2f} "
            f"effective_access={effective_access:.2f} momentum={momentum:.2f} rwr={read_write_ratio:.2f} "
            f"vol={access_volatility:.2f})."
        )

        guardrail_notes: list[str] = []
        classification, recency_guardrail = self._apply_recency_guardrails(
            classification=classification,
            last_access_days=int(resource.last_access_days),
        )
        if recency_guardrail:
            guardrail_notes.append(recency_guardrail)

        archive_guardrail_triggered = False
        classification, archive_guardrail = self._apply_archive_guardrails(
            classification=classification,
            requests_30d=int(resource.requests_30d),
            object_size_bytes=int(resource.object_size_bytes),
            retrieval_penalty=retrieval_penalty,
        )
        if archive_guardrail:
            archive_guardrail_triggered = True
            guardrail_notes.append(archive_guardrail)

        lifecycle_tier = self._lifecycle_tier(last_access_days=int(resource.last_access_days))
        observed_tier = self._coldest_tier(classification, lifecycle_tier)
        if observed_tier != classification:
            guardrail_notes.append(
                f"Lifecycle state applied: {classification} -> {observed_tier} after {resource.last_access_days} idle days."
            )

        if archive_guardrail_triggered and observed_tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            observed_tier = "COLD"
            guardrail_notes.append("Guardrail enforced: archive blocked after lifecycle cooling.")

        prediction = self._predict_target(resource=resource, classification=observed_tier)
        trace.append(
            f"Predicted target={prediction.provider}:{prediction.storage_tier} "
            f"(current={resource.provider}:{resource.current_storage_tier})"
        )

        candidate_cost = current_storage_cost * self._tier_cost_multiplier(prediction.classification)
        cost_pressure = max(current_storage_cost - candidate_cost, 0.0)

        retrieval_penalty_score = self._clamp(retrieval_penalty / RETRIEVAL_PENALTY_MAX)
        access_volatility_score = self._clamp(access_volatility)
        migration_risk = self._clamp(
            0.4 * access_volatility_score + 0.4 * recency_score + 0.2 * retrieval_penalty_score
        )
        risk_cost = migration_risk * max(current_storage_cost, 1.0)

        observation_days = max(int(resource.object_age_days), 1)
        model_confidence = self._clamp(
            min(observation_days / 90.0, float(resource.requests_30d) / 100.0)
        )

        readiness = self._operational_readiness(
            observation_days=observation_days,
            billing_realism=resource.billing_realism,
            integration_permission=resource.integration_permission,
        )

        execution_eligibility = (
            "EXECUTABLE"
            if resource.integration_permission == "READ_WRITE"
            and model_confidence > 0.7
            and migration_risk < RISK_THRESHOLD
            and access_volatility_score < VOLATILITY_UNSTABLE_THRESHOLD
            else "DRY_RUN_ONLY"
        )

        suppression_reasons: list[str] = []
        if model_confidence < MIN_CONFIDENCE_FOR_MIGRATION:
            suppression_reasons.append(
                f"confidence {model_confidence:.2f} below minimum {MIN_CONFIDENCE_FOR_MIGRATION:.2f}"
            )
        if migration_risk >= RISK_HIGH_THRESHOLD:
            suppression_reasons.append(
                f"risk {migration_risk:.2f} above high-risk threshold {RISK_HIGH_THRESHOLD:.2f}"
            )
        if access_volatility_score >= VOLATILITY_UNSTABLE_THRESHOLD:
            suppression_reasons.append(
                f"access volatility {access_volatility_score:.2f} above threshold {VOLATILITY_UNSTABLE_THRESHOLD:.2f}"
            )
        if cost_pressure <= risk_cost:
            suppression_reasons.append(
                f"savings ${cost_pressure:.4f} <= risk_cost ${risk_cost:.4f}"
            )

        if suppression_reasons:
            trace.append("Recommendation suppressed: " + "; ".join(suppression_reasons) + ".")
            action = "RETAIN"
            decision_state = "NO_OP"
            predicted_tier = resource.current_storage_tier
            predicted_provider = resource.provider
        elif prediction.storage_tier.strip().lower() == resource.current_storage_tier.strip().lower():
            action = "RETAIN"
            decision_state = "NO_OP"
            predicted_tier = resource.current_storage_tier
            predicted_provider = resource.provider
            trace.append("No-op: recommended tier matches current placement.")
        else:
            action = "MOVE_TO_PREDICTED_TIER"
            decision_state = "FALLBACK" if guardrail_notes else "PREDICTED"
            predicted_tier = prediction.storage_tier
            predicted_provider = prediction.provider
            trace.append("Predicted action approved after multi-signal evaluation.")

        if guardrail_notes:
            trace.extend([f"Guardrail: {note}" for note in guardrail_notes])

        confidence_trace = {
            "formula": "confidence = min(observation_days/90, requests_30d/100)",
            "observation_days": float(observation_days),
            "requests_30d": float(resource.requests_30d),
            "confidence": round(model_confidence, 6),
        }

        technical_trace = {
            "access_frequency": round(access_frequency, 6),
            "recency_score": round(recency_score, 6),
            "effective_access": round(effective_access, 6),
            "momentum": round(momentum, 6),
            "access_volatility": round(access_volatility, 6),
            "read_write_ratio_clamped": round(read_write_ratio, 6),
            "retrieval_penalty": round(retrieval_penalty, 6),
            "retrieval_penalty_source": retrieval_penalty_source,
            "cost_pressure": round(cost_pressure, 6),
            "temperature_raw": round(temperature_raw, 6),
            "temperature_score": round(temperature_score, 6),
            "migration_risk": round(migration_risk, 6),
            "risk_cost": round(risk_cost, 6),
            "current_storage_cost": round(current_storage_cost, 6),
            "candidate_storage_cost": round(candidate_cost, 6),
            "operational_readiness": readiness,
        }

        return OptimizerDecisionSchema(
            classification=observed_tier,  # type: ignore[arg-type]
            action=action,  # type: ignore[arg-type]
            decision_state=decision_state,  # type: ignore[arg-type]
            recommended_provider=predicted_provider,  # type: ignore[arg-type]
            recommended_storage_tier=predicted_tier,
            observed_tier=observed_tier,
            intent_tier=resource.intent_tier,
            observed_temperature=classification,
            access_frequency=round(access_frequency, 6),
            recency_score=round(recency_score, 6),
            effective_access=round(effective_access, 6),
            access_recency_score=round(recency_score, 6),
            temperature_score=round(temperature_score, 6),
            estimated_savings=round(cost_pressure, 6),
            confidence_final=round(model_confidence, 6),
            model_confidence=round(model_confidence, 6),
            migration_risk=round(migration_risk, 6),
            execution_eligibility=execution_eligibility,  # type: ignore[arg-type]
            confidence_trace=confidence_trace,
            rule_trace=trace,
            technical_trace=technical_trace,
        )

    def _classify_temperature(self, *, temperature_score: float) -> str:
        if temperature_score >= 7.0:
            return "HOT"
        if temperature_score >= 5.0:
            return "WARM"
        if temperature_score >= 3.0:
            return "COLD"
        return "ARCHIVE"

    def _normalize_temperature(self, raw_score: float) -> float:
        if TEMPERATURE_RAW_MAX <= 0:
            return 0.0
        normalized = (raw_score / TEMPERATURE_RAW_MAX) * 10.0
        return max(0.0, min(10.0, normalized))

    def _apply_recency_guardrails(self, *, classification: str, last_access_days: int) -> tuple[str, str | None]:
        if last_access_days < 7:
            return "HOT", "Recent access < 7 days forced HOT."
        if last_access_days < 30 and classification in {"ARCHIVE", "DEEP_ARCHIVE"}:
            return "COLD", "Recent access < 30 days prevents archive."
        return classification, None

    def _apply_archive_guardrails(
        self,
        *,
        classification: str,
        requests_30d: int,
        object_size_bytes: int,
        retrieval_penalty: float,
    ) -> tuple[str, str | None]:
        if classification not in {"ARCHIVE", "DEEP_ARCHIVE"}:
            return classification, None
        if requests_30d > ARCHIVE_REQUESTS_THRESHOLD:
            return "COLD", "Archive prevented: retrieval workload too high."
        object_size_tb = float(object_size_bytes) / (1024.0 ** 4)
        if object_size_tb > LARGE_OBJECT_TB and retrieval_penalty > RETRIEVAL_PENALTY_MAX:
            return "COLD", "Archive prevented: large object with high retrieval penalty."
        return classification, None

    def _lifecycle_tier(self, *, last_access_days: int) -> str:
        if last_access_days < 30:
            return "HOT"
        if last_access_days < 90:
            return "WARM"
        if last_access_days < 180:
            return "COLD"
        if last_access_days < 365:
            return "ARCHIVE"
        return "DEEP_ARCHIVE"

    def _coldest_tier(self, tier_a: str, tier_b: str) -> str:
        order = {"HOT": 0, "WARM": 1, "COLD": 2, "ARCHIVE": 3, "DEEP_ARCHIVE": 4}
        return tier_a if order.get(tier_a, 0) >= order.get(tier_b, 0) else tier_b

    def _predict_target(self, *, resource: ResourceIngestItem, classification: str) -> Prediction:
        provider = resource.provider
        tier = classification
        if provider == "AWS":
            mapping = {
                "HOT": "STANDARD",
                "WARM": "STANDARD_IA",
                "COLD": "GLACIER",
                "ARCHIVE": "GLACIER",
                "DEEP_ARCHIVE": "DEEP_ARCHIVE",
            }
        elif provider == "GCP":
            mapping = {
                "HOT": "STANDARD",
                "WARM": "NEARLINE",
                "COLD": "COLDLINE",
                "ARCHIVE": "ARCHIVE",
                "DEEP_ARCHIVE": "ARCHIVE",
            }
        else:
            mapping = {
                "HOT": "HOT_BLOB",
                "WARM": "COOL_BLOB",
                "COLD": "ARCHIVE_BLOB",
                "ARCHIVE": "ARCHIVE_BLOB",
                "DEEP_ARCHIVE": "ARCHIVE_BLOB",
            }
        return Prediction(provider=provider, storage_tier=mapping.get(tier, "STANDARD"), classification=tier)

    def _tier_cost_multiplier(self, tier: str) -> float:
        return {
            "HOT": 1.0,
            "WARM": 0.7,
            "COLD": 0.4,
            "ARCHIVE": 0.2,
            "DEEP_ARCHIVE": 0.1,
        }.get(tier, 1.0)

    def _operational_readiness(self, *, observation_days: int, billing_realism: str, integration_permission: str) -> str:
        if billing_realism == "ESTIMATE" or observation_days < 30:
            return "LOW"
        if integration_permission != "READ_WRITE":
            return "MEDIUM"
        return "HIGH"

    def _clamp(self, value: float) -> float:
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return float(value)
