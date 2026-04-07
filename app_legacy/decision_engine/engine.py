"""Hybrid rule-based + ML decision engine."""

from __future__ import annotations

from app.collectors.models import ObjectUsageSnapshot
from app.core.monitoring import (
    record_ml_confidence,
    record_migration_result,
    record_objects_per_data_class,
    record_savings,
    record_storage_cost,
)
from app.decision_engine.models import ClassificationOutcome, ObjectOptimizationDecision, OptimizationReport
from app.decision_engine.types import DecisionAction, DecisionMode
from app.feature_engineering.extractor import FeatureEngineeringService
from app.ml_engine.model import StorageMLClassifier
from app.migration_engine.engine import MigrationEngine, MigrationRequest
from app.migration_engine.gateways import ObjectReference
from app.pricing_engine.engine import MultiCloudPricingEngine
from app.rules_engine.policy import RuleBasedStorageClassifier


class HybridDecisionEngine:
    """Combines rule and ML outputs with confidence-based fallback."""

    def __init__(
        self,
        feature_service: FeatureEngineeringService,
        rules: RuleBasedStorageClassifier,
        pricing: MultiCloudPricingEngine,
        ml_model: StorageMLClassifier | None = None,
        migration_engine: MigrationEngine | None = None,
    ):
        self._features = feature_service
        self._rules = rules
        self._pricing = pricing
        self._ml = ml_model
        self._migration = migration_engine

    async def optimize_snapshots(
        self,
        snapshots: list[ObjectUsageSnapshot],
        mode: DecisionMode,
        currency: str,
        ml_confidence_threshold: float,
        allowed_regions: dict[str, list[str]] | None = None,
        delete_source_after_migration: bool = False,
    ) -> OptimizationReport:
        """Evaluate all objects and return transparent recommendations."""
        decisions: list[ObjectOptimizationDecision] = []

        for snapshot in snapshots:
            feature = self._features.build_feature(snapshot)
            rule_result = self._rules.classify(feature)

            selected_class = rule_result.data_class
            selected_confidence = rule_result.confidence
            source = "rule_based"
            fallback_used = False
            ml_confidence: float | None = None
            reasoning = list(rule_result.reasoning)

            if self._ml and self._ml.is_trained:
                ml_prediction = self._ml.predict(feature)
                ml_confidence = ml_prediction.confidence
                record_ml_confidence(ml_prediction.confidence)

                if ml_prediction.confidence >= ml_confidence_threshold:
                    selected_class = ml_prediction.predicted_class
                    selected_confidence = ml_prediction.confidence
                    source = "ml"
                    reasoning.insert(
                        0,
                        (
                            "ML confidence "
                            f"{ml_prediction.confidence:.3f} >= threshold {ml_confidence_threshold:.3f}; "
                            f"using ML class {ml_prediction.predicted_class.value}"
                        ),
                    )
                else:
                    fallback_used = True
                    reasoning.insert(
                        0,
                        (
                            "ML confidence "
                            f"{ml_prediction.confidence:.3f} < threshold {ml_confidence_threshold:.3f}; "
                            "fallback to rule classification"
                        ),
                    )

            classification = ClassificationOutcome(
                selected_class=selected_class,
                source=source,
                confidence=round(selected_confidence, 6),
                rule_confidence=round(rule_result.confidence, 6),
                ml_confidence=round(ml_confidence, 6) if ml_confidence is not None else None,
                fallback_used=fallback_used,
                reasoning=reasoning,
            )

            options = await self._pricing.evaluate_options(
                feature=feature,
                data_class=selected_class,
                currency=currency,
                allowed_regions=allowed_regions,
            )
            if not options:
                continue

            best_option = options[0]

            try:
                current_cost = await self._pricing.estimate_current_cost(
                    feature=feature,
                    provider=snapshot.inventory.provider,
                    region=snapshot.inventory.region,
                    tier=snapshot.inventory.storage_tier,
                    currency=currency,
                )
            except KeyError:
                current_cost = best_option

            monthly_savings = max(
                0.0,
                current_cost.total_monthly_converted - best_option.total_monthly_converted,
            )
            yearly_savings = max(
                0.0,
                current_cost.total_yearly_converted - best_option.total_yearly_converted,
            )

            same_location = (
                snapshot.inventory.provider == best_option.provider
                and snapshot.inventory.region == best_option.region
                and snapshot.inventory.storage_tier == best_option.tier
            )
            should_migrate = not same_location and monthly_savings > 0
            action = DecisionAction.MIGRATE if should_migrate else DecisionAction.KEEP

            migration_payload = None
            if should_migrate and self._migration:
                migration_result = await self._migration.migrate(
                    MigrationRequest(
                        tenant_id=snapshot.tenant_id,
                        object_id=snapshot.object_id,
                        source=ObjectReference(
                            provider=snapshot.inventory.provider,
                            region=snapshot.inventory.region,
                            bucket=snapshot.inventory.bucket,
                            key=snapshot.inventory.object_key,
                        ),
                        target=ObjectReference(
                            provider=best_option.provider,
                            region=best_option.region,
                            bucket=snapshot.inventory.bucket,
                            key=snapshot.inventory.object_key,
                        ),
                        target_tier=best_option.tier,
                        dry_run=mode != DecisionMode.ENFORCED,
                        delete_source_after_copy=delete_source_after_migration,
                    )
                )
                migration_payload = migration_result.to_dict()
                record_migration_result(migration_result.status)

            record_storage_cost(best_option.provider, best_option.region, best_option.total_monthly_usd)
            record_savings(snapshot.tenant_id, monthly_savings)
            record_objects_per_data_class(selected_class.value)

            explanation = (
                f"Selected {selected_class.value} using {classification.source}; "
                f"current={snapshot.inventory.provider}/{snapshot.inventory.region}/{snapshot.inventory.storage_tier}, "
                f"recommended={best_option.provider}/{best_option.region}/{best_option.tier}, "
                f"monthly_savings={monthly_savings:.2f} {currency.upper()}"
            )

            decisions.append(
                ObjectOptimizationDecision(
                    tenant_id=snapshot.tenant_id,
                    object_id=snapshot.object_id,
                    current_provider=snapshot.inventory.provider,
                    current_region=snapshot.inventory.region,
                    current_tier=snapshot.inventory.storage_tier,
                    recommended_provider=best_option.provider,
                    recommended_region=best_option.region,
                    recommended_tier=best_option.tier,
                    mode=mode,
                    action=action,
                    classification=classification,
                    current_cost=current_cost.to_dict(),
                    recommended_cost=best_option.to_dict(),
                    alternatives=[option.to_dict() for option in options[:10]],
                    estimated_monthly_savings=round(monthly_savings, 6),
                    estimated_yearly_savings=round(yearly_savings, 6),
                    explanation=explanation,
                    migration=migration_payload,
                )
            )

        return OptimizationReport(decisions=decisions, currency=currency, mode=mode)
