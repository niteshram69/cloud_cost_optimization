from collections import Counter, defaultdict
import math
from pathlib import Path
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    BucketAggregate,
    BucketObjectReference,
    DataTemperature,
    DataSource,
    DataSourceType,
    DecisionState,
    ExecutionEligibility,
    IngestionJob,
    IngestedRecord,
    MigrationLifecycleState,
    MigrationJob,
    PricingConfidence,
    Recommendation,
    RecommendationStatus,
    StoragePricingRecord,
    StorageRecord,
)
from backend.app.schemas.dashboard import (
    DataTemperatureResponse,
    GroupedRecommendationResponse,
    ProviderAuthorityResponse,
    RecommendationResponse,
    RecommendationSummaryResponse,
    SummaryResponse,
    UserMigrationResponse,
)
from backend.app.services.confidence_scoring_service import ConfidenceDecayInputs, apply_confidence_decay
from backend.app.services.pricing_intelligence_service import PricingDecisionService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, user_id: int) -> SummaryResponse:
        latest_job = self._latest_ingestion_job(user_id=user_id)
        dataset_id = latest_job.id if latest_job else None
        bucket_rows = self.db.scalars(select(BucketAggregate).where(BucketAggregate.user_id == user_id)).all()
        temperature_counts: Counter[DataTemperature] = Counter()
        total_cost = 0.0
        estimated_savings = 0.0

        if bucket_rows:
            for row in bucket_rows:
                effective_cost = (
                    float(row.actual_monthly_cost_usd)
                    if row.has_real_billing and row.actual_monthly_cost_usd is not None
                    else float(row.estimated_monthly_cost_usd)
                )
                total_cost += max(effective_cost, 0.0)
                temperature_counts[row.temperature] += 1

            bucket_ids = [row.bucket_id for row in bucket_rows]
            if bucket_ids:
                savings_query = select(func.coalesce(func.sum(Recommendation.estimated_monthly_savings), 0)).where(
                    Recommendation.user_id == user_id,
                    Recommendation.status == RecommendationStatus.OPEN,
                    Recommendation.resource_name.in_(bucket_ids),
                )
                if dataset_id is not None:
                    savings_query = savings_query.where(Recommendation.dataset_id == dataset_id)
                estimated_savings = float(self.db.scalar(savings_query) or 0.0)
            raw_total_count = len(bucket_rows)
        else:
            total_cost, estimated_savings, raw_total_count = self.db.execute(
                select(
                    func.coalesce(func.sum(StorageRecord.storage_cost), 0),
                    func.coalesce(func.sum(StorageRecord.estimated_savings), 0),
                    func.count(StorageRecord.id),
                ).where(StorageRecord.user_id == user_id)
            ).one()

            grouped = self.db.execute(
                select(StorageRecord.temperature, func.count(StorageRecord.id))
                .where(StorageRecord.user_id == user_id)
                .group_by(StorageRecord.temperature)
            ).all()
            for temp, count in grouped:
                temperature_counts[temp] = int(count)

        total_count = max(1, int(raw_total_count or 0))
        latest_pricing_version = self.db.scalar(
            select(StoragePricingRecord.pricing_version)
            .order_by(desc(StoragePricingRecord.effective_date), desc(StoragePricingRecord.created_at))
            .limit(1)
        )
        integration_authority_by_provider = self._integration_authority_by_provider(user_id=user_id)
        provider_authority: list[ProviderAuthorityResponse] = []
        for provider in ("AWS", "AZURE", "GCP"):
            ingestion_mode, integration_permission = integration_authority_by_provider.get(provider, ("USER_UPLOAD", "NONE"))
            execution_authorized = ingestion_mode == "CLOUD_INTEGRATION" and integration_permission == "READ_WRITE"
            if execution_authorized:
                reason = "Write-enabled cloud integration active."
            elif ingestion_mode != "CLOUD_INTEGRATION":
                reason = "No cloud integration connected. Dry-run simulation remains available."
            elif integration_permission != "READ_WRITE":
                reason = "Connected integration is read-only. Dry-run simulation remains available."
            else:
                reason = "Execution authority unavailable."

            provider_authority.append(
                ProviderAuthorityResponse(
                    provider=provider,
                    ingestion_mode=ingestion_mode,
                    integration_permission=integration_permission,
                    mode="EXECUTION_MODE" if execution_authorized else "ANALYSIS_MODE",
                    execution_authorized=execution_authorized,
                    reason=reason,
                )
            )

        has_execution_authority = any(item.execution_authorized for item in provider_authority)
        dataset_label = self._dataset_label(latest_job) if latest_job else None
        dataset_source = str(latest_job.data_origin) if latest_job else None
        dataset_source_label = self._dataset_source_label(latest_job) if latest_job else None
        dataset_record_count = int(latest_job.record_count) if latest_job else None
        dataset_created_at = latest_job.created_at if latest_job else None

        return SummaryResponse(
            total_storage_cost=round(float(total_cost or 0), 4),
            estimated_monthly_savings=round(float(estimated_savings or 0), 4),
            hot_percentage=round(temperature_counts[DataTemperature.HOT] * 100 / total_count, 2),
            cold_percentage=round(temperature_counts[DataTemperature.COLD] * 100 / total_count, 2),
            archive_percentage=round(temperature_counts[DataTemperature.ARCHIVE] * 100 / total_count, 2),
            pricing_version=str(latest_pricing_version) if latest_pricing_version else None,
            system_mode="EXECUTION_MODE" if has_execution_authority else "ANALYSIS_MODE",
            analysis_ready=True,
            execution_authorized=has_execution_authority,
            provider_authority=provider_authority,
            dataset_id=dataset_id,
            dataset_label=dataset_label,
            dataset_source=dataset_source,
            dataset_source_label=dataset_source_label,
            dataset_record_count=dataset_record_count,
            dataset_created_at=dataset_created_at,
        )

    def get_recommendations(self, user_id: int) -> list[RecommendationResponse]:
        latest_job = self._latest_ingestion_job(user_id=user_id)
        if not latest_job:
            return []
        dataset_id = latest_job.id
        bucket_by_id = self._latest_bucket_by_bucket_id(user_id=user_id)
        bucket_ids = set(bucket_by_id.keys())
        base_query = select(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.status == RecommendationStatus.OPEN,
            Recommendation.dataset_id == dataset_id,
        )
        if bucket_ids:
            rows = self.db.scalars(
                base_query
                .where(Recommendation.resource_name.in_(bucket_ids))
                .order_by(desc(Recommendation.estimated_monthly_savings))
                .limit(100)
            ).all()
            if not rows:
                rows = self.db.scalars(
                    base_query.order_by(desc(Recommendation.estimated_monthly_savings)).limit(100)
                ).all()
        else:
            rows = self.db.scalars(
                base_query.order_by(desc(Recommendation.estimated_monthly_savings)).limit(100)
            ).all()

        resource_names = {row.resource_name for row in rows}
        storage_by_resource = self._latest_storage_by_resource(user_id=user_id, resource_names=resource_names)
        feature_snapshot_by_resource = self._latest_feature_snapshot_by_resource(
            user_id=user_id,
            resource_names=resource_names,
        )
        pricing_service = PricingDecisionService(self.db)
        latest_pricing_version = self.db.scalar(
            select(StoragePricingRecord.pricing_version)
            .order_by(desc(StoragePricingRecord.effective_date), desc(StoragePricingRecord.created_at))
            .limit(1)
        )
        integration_authority_by_provider = self._integration_authority_by_provider(user_id=user_id)

        responses: list[RecommendationResponse] = []
        for row in rows:
            bucket = bucket_by_id.get(row.resource_name)
            if bucket is None:
                bucket = self._bucket_for_resource(user_id=user_id, resource_name=row.resource_name)
            storage = storage_by_resource.get(row.resource_name)
            feature_snapshot_source = feature_snapshot_by_resource.get(row.resource_name, {})

            optimization_unit = "BUCKET" if bucket else "OBJECT"
            if bucket:
                base_confidence = float(bucket.classification_confidence or 0.62)
                est_cost = (
                    float(bucket.actual_monthly_cost_usd)
                    if bucket.has_real_billing and bucket.actual_monthly_cost_usd is not None
                    else float(bucket.estimated_monthly_cost_usd)
                )
                data_temperature = bucket.temperature
                temp = data_temperature.value
                access_frequency = int(round(max(float(bucket.total_requests_30d), 0.0)))
                read_write_ratio = 6.0 if temp == "HOT" else 2.2 if temp == "COLD" else 0.8
                object_size_mb = round(max(float(bucket.avg_object_size_gb) * 1024.0, 0.0), 2)
                object_count = max(int(bucket.total_objects), 0)
                total_size_gb = max(float(bucket.total_size_gb), 0.0)
                observation_days = max(int(bucket.observation_days), 1)
                billing_present = bool(bucket.has_real_billing and bucket.actual_monthly_cost_usd is not None)
                region = bucket.region
                current_provider = bucket.cloud_provider.value
                bucket_metrics: dict[str, float | int | str | bool] | None = {
                    "bucket_id": bucket.bucket_id,
                    "cloud_provider": bucket.cloud_provider.value,
                    "region": bucket.region,
                    "storage_class": bucket.storage_class,
                    "total_objects": bucket.total_objects,
                    "total_size_gb": round(float(bucket.total_size_gb), 6),
                    "avg_object_size_gb": round(float(bucket.avg_object_size_gb), 6),
                    "total_requests_30d": round(float(bucket.total_requests_30d), 6),
                    "avg_requests_per_object": round(float(bucket.avg_requests_per_object), 6),
                    "estimated_monthly_cost_usd": round(float(bucket.estimated_monthly_cost_usd), 6),
                    "actual_monthly_cost_usd": round(float(bucket.actual_monthly_cost_usd), 6)
                    if bucket.actual_monthly_cost_usd is not None
                    else 0.0,
                    "has_real_billing": billing_present,
                }
                object_references = list(bucket.object_references or [])
                last_access_days = None
                requests_90d = None
                access_std_dev = None
                object_age_days = observation_days
            else:
                base_confidence = float(storage.classification_confidence) if storage else 0.62
                est_cost = float(storage.storage_cost) if storage else max(row.estimated_monthly_savings * 2.0, 10.0)
                data_temperature = storage.temperature if storage else DataTemperature.COLD
                temp = data_temperature.value
                access_frequency_raw = feature_snapshot_source.get("last_30d_access_frequency")
                read_write_ratio_raw = feature_snapshot_source.get("read_write_ratio")
                object_size_raw = feature_snapshot_source.get("object_size_mb")
                last_access_days_raw = feature_snapshot_source.get("last_access_days")
                requests_90d_raw = feature_snapshot_source.get("requests_90d")
                access_std_dev_raw = feature_snapshot_source.get("access_std_dev")
                object_age_days_raw = feature_snapshot_source.get("object_age_days")
                access_frequency = (
                    int(round(float(access_frequency_raw)))
                    if isinstance(access_frequency_raw, (int, float))
                    else (90 if temp == "HOT" else 25 if temp == "COLD" else 4)
                )
                read_write_ratio = (
                    round(float(read_write_ratio_raw), 3)
                    if isinstance(read_write_ratio_raw, (int, float))
                    else (6.0 if temp == "HOT" else 2.2 if temp == "COLD" else 0.8)
                )
                object_size_mb = (
                    round(max(float(object_size_raw), 0.0), 2)
                    if isinstance(object_size_raw, (int, float))
                    else None
                )
                last_access_days = (
                    int(round(float(last_access_days_raw)))
                    if isinstance(last_access_days_raw, (int, float))
                    else None
                )
                requests_90d = (
                    int(round(float(requests_90d_raw)))
                    if isinstance(requests_90d_raw, (int, float))
                    else None
                )
                access_std_dev = (
                    round(float(access_std_dev_raw), 4)
                    if isinstance(access_std_dev_raw, (int, float))
                    else None
                )
                object_age_days = (
                    int(round(float(object_age_days_raw)))
                    if isinstance(object_age_days_raw, (int, float))
                    else None
                )
                object_count = 1
                total_size_gb = max((object_size_mb or 1024.0) / 1024.0, 1.0)
                observation_days = 30
                billing_present = False
                region = storage.region if storage else "global"
                current_provider = storage.provider.value if storage else row.recommended_provider.value
                bucket_metrics = None
                object_references = [row.resource_name]

            confidence = float(base_confidence)
            confidence_band = self._confidence_band(confidence=confidence)
            decision_state = DecisionState.EXPLORATORY

            recommended_provider = row.recommended_provider.value
            recommended_tier = row.recommended_tier
            ingestion_mode, integration_permission = integration_authority_by_provider.get(
                current_provider.upper(),
                ("USER_UPLOAD", "NONE"),
            )
            monthly_savings = float(row.estimated_monthly_savings)
            current_monthly_cost: float | None = round(max(est_cost, 0.0), 4)
            optimized_monthly_cost: float | None = None
            estimated_savings_percent: float | None = None
            pricing_version: str | None = bucket.pricing_version if bucket and bucket.pricing_version else None
            pricing_candidates: list[dict[str, float | int | str]] = []
            all_pricing_candidates = []
            pricing_trace: str | None = None

            try:
                decision = pricing_service.decide_for_storage_record(
                    resource_id=(bucket.bucket_id if bucket else row.resource_name),
                    data_temperature=data_temperature,
                    region=region,
                    current_cloud=current_provider,
                    current_tier=row.current_tier,
                    current_monthly_cost=max(est_cost, 0.0),
                )
                recommended_provider = decision.recommended_cloud
                recommended_tier = decision.recommended_tier
                current_monthly_cost = round(decision.current_monthly_cost, 4)
                optimized_monthly_cost = round(decision.optimized_monthly_cost, 4)
                estimated_savings_percent = round(decision.estimated_savings_percent, 2)
                pricing_version = decision.pricing_version
                monthly_savings = round(max(decision.current_monthly_cost - decision.optimized_monthly_cost, 0.0), 4)
                all_pricing_candidates = decision.candidates
                pricing_candidates = [
                    {
                        "cloud": candidate.cloud,
                        "native_tier": candidate.native_tier,
                        "region": candidate.region,
                        "monthly_cost": round(candidate.monthly_cost, 4),
                        "storage_price_per_gb": round(candidate.storage_price_per_gb, 6),
                        "retrieval_price_per_gb": round(candidate.retrieval_price_per_gb, 6),
                        "currency": candidate.currency,
                    }
                    for candidate in decision.candidates[:6]
                ]
                pricing_trace = (
                    f"Pricing decision v{decision.pricing_version}: "
                    f"current=${decision.current_monthly_cost:.2f}, optimized=${decision.optimized_monthly_cost:.2f}"
                )
            except ValueError:
                pass

            ml_predicted_tier = recommended_tier
            ml_predicted_provider = recommended_provider
            predicted_tier = ml_predicted_tier
            predicted_provider = ml_predicted_provider
            guardrail_notes: list[str] = []

            if data_temperature == DataTemperature.HOT and self._is_archive_tier(predicted_tier):
                predicted_provider = current_provider
                predicted_tier = self._safe_hot_tier(current_provider)
                guardrail_notes.append("Guardrail enforced: HOT data cannot move to ARCHIVE.")

            safe_tier = self.apply_latency_guardrail(
                ml_prediction=f"{predicted_provider}:{predicted_tier}",
                access_count_30d=access_frequency,
                current_provider=current_provider,
            )
            if safe_tier == "STAY_IN_CURRENT_PROVIDER":
                predicted_provider = current_provider
                predicted_tier = row.current_tier
                guardrail_notes.append(
                    "Latency/Egress guardrail enforced: high-access cross-cloud move blocked; staying in current provider."
                )
            elif safe_tier != predicted_tier:
                predicted_tier = safe_tier
                guardrail_notes.append(
                    f"Latency guardrail enforced: high-access archive recommendation downgraded to '{safe_tier}'."
                )

            pricing_confidence = self._pricing_confidence(
                has_real_billing=billing_present,
                pricing_version=pricing_version,
            )
            billing_realism = self._billing_realism(pricing_confidence=pricing_confidence)
            data_maturity, data_maturity_score = self._derive_data_maturity(
                ingestion_mode=ingestion_mode,
                observation_days=observation_days,
                object_count=object_count,
                total_size_gb=total_size_gb,
                billing_realism=billing_realism,
            )
            pricing_drift_detected = bool(
                latest_pricing_version
                and pricing_version
                and str(pricing_version) != str(latest_pricing_version)
            )
            hard_guardrail_block = False
            if pricing_drift_detected:
                decision_state = DecisionState.BLOCKED
                hard_guardrail_block = True
                guardrail_notes.append(
                    f"Pricing drift detected ({pricing_version} vs latest {latest_pricing_version}); execution blocked."
                )

            decay = apply_confidence_decay(
                ConfidenceDecayInputs(
                    confidence_base=base_confidence,
                    object_count=max(object_count, 1),
                    total_size_gb=max(total_size_gb, 0.0),
                    observation_days=max(observation_days, 1),
                    pricing_confidence=pricing_confidence.value,
                    optimization_unit=optimization_unit,
                    is_cross_cloud_move=predicted_provider.upper() != current_provider.upper(),
                    access_count_30d=float(access_frequency),
                )
            )
            confidence = float(decay.confidence_final)
            confidence_band = self._confidence_band(confidence=confidence)
            model_confidence = self._clamp_01(base_confidence)
            operational_readiness = self._operational_readiness_score(
                data_window_factor=decay.data_window_factor,
                billing_realism_factor=decay.billing_realism_factor,
                aggregation_factor=decay.aggregation_factor,
                data_maturity_score=data_maturity_score,
            )
            operational_readiness_band = self._operational_readiness_band(operational_readiness)
            operational_readiness_reasons = self._operational_readiness_reasons(
                data_window_factor=decay.data_window_factor,
                billing_realism_factor=decay.billing_realism_factor,
                aggregation_factor=decay.aggregation_factor,
                data_maturity=data_maturity,
                billing_realism=billing_realism,
            )

            if decision_state == DecisionState.BLOCKED:
                action_name = "RETAIN"
                recommended_provider = current_provider
                recommended_tier = row.current_tier
                final_decision = "Optimization blocked due to pricing-version drift."
            elif decay.policy_action == "MOVE_TO_PREDICTED_TIER":
                decision_state = DecisionState.PREDICTED
                action_name = "MOVE_TO_PREDICTED_TIER"
                recommended_provider = predicted_provider
                recommended_tier = predicted_tier
                final_decision = "Predicted action approved after confidence and guardrail checks."
            elif decay.policy_action == "MOVE_TO_STANDARD_IA":
                decision_state = DecisionState.FALLBACK
                action_name = "MOVE_TO_STANDARD_IA"
                recommended_provider = current_provider
                recommended_tier = "Standard-IA"
                final_decision = "Safety fallback due to confidence decay."
            else:
                recommended_provider = predicted_provider
                recommended_tier = predicted_tier
                if str(recommended_tier).strip().lower() == str(row.current_tier).strip().lower():
                    decision_state = DecisionState.NO_OP
                    action_name = "RETAIN"
                    final_decision = "No-op recommendation: recommended tier matches current tier."
                else:
                    decision_state = DecisionState.FALLBACK
                    action_name = "PROPOSED"
                    final_decision = (
                        "Proposed recommendation retained for dry-run due maturity/uncertainty; not auto-executed."
                    )

            if data_temperature == DataTemperature.HOT and self._is_archive_tier(recommended_tier):
                decision_state = DecisionState.BLOCKED
                action_name = "RETAIN"
                recommended_provider = current_provider
                recommended_tier = row.current_tier
                hard_guardrail_block = True
                guardrail_notes.append("Guardrail re-applied after policy to keep HOT data in accessible tier.")
                final_decision = "Optimization blocked by HOT-data accessibility guardrail."

            same_tier = str(recommended_tier).strip().lower() == str(row.current_tier).strip().lower()
            if same_tier and decision_state != DecisionState.BLOCKED:
                decision_state = DecisionState.NO_OP
                action_name = "RETAIN"

            hard_block = bool(decision_state == DecisionState.BLOCKED or hard_guardrail_block)
            is_cross_cloud = recommended_provider.upper() != current_provider.upper()
            execution_authority = self._derive_execution_authority(
                ingestion_mode=ingestion_mode,
                integration_permission=integration_permission,
            )
            execution_eligibility, execution_reason = self._derive_execution_eligibility(
                execution_authority=execution_authority,
                hard_block=hard_block,
                is_cross_cloud=is_cross_cloud,
            )
            execution_unlock_hint = self._execution_unlock_hint(
                ingestion_mode=ingestion_mode,
                integration_permission=integration_permission,
                execution_authority=execution_authority,
                execution_eligibility=execution_eligibility,
                hard_block=hard_block,
            )

            if hard_block:
                recommendation_state = "BLOCKED_BY_GUARDRAIL"
            elif execution_eligibility == ExecutionEligibility.NONE:
                recommendation_state = "BLOCKED_BY_AUTHORITY"
            elif execution_eligibility == ExecutionEligibility.DRY_RUN_ELIGIBLE:
                recommendation_state = "READY_FOR_DRY_RUN"
            else:
                recommendation_state = "READY_FOR_EXECUTION"
            recommendation_action = "NO_OP" if decision_state == DecisionState.NO_OP else "PROPOSED"

            storage_gb_estimate = max(total_size_gb, 1.0)
            if bucket is None:
                current_tier_rate = self._fallback_rate_for_tier(row.current_tier)
                if current_tier_rate and current_tier_rate > 0:
                    storage_gb_estimate = max(float(est_cost) / current_tier_rate, 1.0)
                else:
                    storage_gb_estimate = self._estimate_storage_gb_from_cost(
                        data_temperature=data_temperature,
                        monthly_cost=est_cost,
                    )
            if object_size_mb is None or object_size_mb <= 0:
                object_size_mb = round(max(storage_gb_estimate * 1024.0, 0.0), 2)

            if current_monthly_cost is not None and decision_state == DecisionState.PREDICTED:
                candidate_cost = self._find_candidate_monthly_cost(
                    candidates=all_pricing_candidates,
                    provider=recommended_provider,
                    tier=recommended_tier,
                )
                if candidate_cost is not None:
                    optimized_monthly_cost = round(candidate_cost, 4)
                else:
                    fallback_rate = self._fallback_rate_for_tier(recommended_tier)
                    if fallback_rate is not None:
                        optimized_monthly_cost = round(storage_gb_estimate * fallback_rate, 4)
                        guardrail_notes.append(
                            f"Pricing fallback used for tier '{recommended_tier}' at ${fallback_rate:.6f}/GB."
                        )
                    else:
                        optimized_monthly_cost = current_monthly_cost

            (
                current_monthly_cost,
                optimized_monthly_cost,
                monthly_savings,
                estimated_savings_percent,
            ) = self._apply_pricing_clamp(
                decision_state=decision_state,
                before_cost=current_monthly_cost,
                after_cost=optimized_monthly_cost,
            )
            if decision_state != DecisionState.PREDICTED:
                pricing_candidates = []

            trace = [
                f"Optimization Unit: {optimization_unit}",
                f"ML Prediction: {ml_predicted_provider} {ml_predicted_tier}",
                f"Recommendation Action: {recommendation_action}",
                f"Recommendation State: {recommendation_state}",
                f"Decision State: {decision_state.value}",
                f"Execution Eligibility: {execution_eligibility.value}",
                f"Execution Authority: {execution_authority}",
                f"Operational Readiness: {operational_readiness * 100:.2f}% ({operational_readiness_band})",
                f"Confidence Decay: base={base_confidence:.4f}, final={confidence:.4f}, "
                f"factors(window={decay.data_window_factor:.2f}, billing={decay.billing_realism_factor:.2f}, "
                f"aggregation={decay.aggregation_factor:.2f}, migration={decay.migration_risk_factor:.2f})",
                f"Logic Check: Confidence is {confidence_band} ({billing_realism})",
                f"Final Decision: {final_decision}",
            ]
            if decay.downgrade_reasons:
                trace.extend(decay.downgrade_reasons)
            if guardrail_notes:
                trace.extend(guardrail_notes)
            if pricing_trace:
                trace.append(pricing_trace)

            confidence_percentage = round(confidence * 100.0, 2)
            decision_trace_block = (
                f"[{row.resource_name}]\n"
                f"ACTION: {recommendation_action}\n"
                f"STATE: {recommendation_state}\n"
                f"ENGINE_STATE: {decision_state.value}\n"
                f"Confidence: {confidence_percentage:.2f}%\n"
                f"Savings Potential: ${monthly_savings:.2f}/mo\n"
                "Rule Trace:\n"
                f"- Optimization Unit: {optimization_unit}\n"
                f"- Confidence Decay: base={base_confidence:.4f}, final={confidence:.4f}\n"
                f"- Data Maturity: {data_maturity}\n"
                f"- Billing Realism: {billing_realism}\n"
                f"- Execution Authority: {execution_authority}\n"
                f"- Execution Eligibility: {execution_eligibility.value}\n"
                f"- Execution Reason: {execution_reason}\n"
                f"- Unlock Path: {execution_unlock_hint}\n"
                f"- Final Decision: {final_decision}"
            )
            if guardrail_notes:
                decision_trace_block += "".join(f"\n- {note}" for note in guardrail_notes)
            if decay.downgrade_reasons:
                decision_trace_block += "".join(f"\n- {note}" for note in decay.downgrade_reasons)

            cost_assumptions = {
                "monthly_access_rate": f"{self._retrieval_ratio_for_temp(data_temperature) * 100:.2f}%",
                "egress_costs": "excluded",
                "min_storage_duration": "honored",
            }
            migration_advisory = self._build_migration_advisory(
                current_provider=current_provider,
                recommended_provider=recommended_provider,
                recommended_tier=recommended_tier,
                confidence=confidence,
                storage_gb=storage_gb_estimate,
                decision_state=decision_state,
                pricing_confidence=pricing_confidence,
                execution_eligibility=execution_eligibility,
                execution_reason=execution_reason,
            )
            confidence_message = (
                "Confidence downgraded due to dataset coverage constraints."
                if decay.downgrade_reasons
                else "Confidence retained with sufficient volume/time/billing evidence."
            )
            if decision_state == DecisionState.FALLBACK:
                confidence_message = "Safety fallback due to confidence decay."
            if decision_state == DecisionState.BLOCKED:
                confidence_message = "Execution blocked by policy/guardrail."
            if recommendation_state == "READY_FOR_DRY_RUN":
                confidence_message = "Dry-run is available; direct execution requires stronger authority and approvals."

            pricing_trace_payload = {
                "pricing_version_used": pricing_version,
                "latest_pricing_version": str(latest_pricing_version) if latest_pricing_version else None,
                "pricing_drift_detected": pricing_drift_detected,
                "pricing_source": recommended_provider if decision_state == DecisionState.PREDICTED else current_provider,
                "pricing_confidence": pricing_confidence.value,
                "exploration_suppressed": decision_state != DecisionState.PREDICTED,
                "before_cost_usd": current_monthly_cost,
                "after_cost_usd": optimized_monthly_cost,
            }
            feature_snapshot_payload: dict[str, float | int | str] = {
                "temperature": temp,
                "last_30d_access_frequency": access_frequency,
                "read_write_ratio": read_write_ratio,
                "estimated_monthly_cost_usd": round(est_cost, 2),
            }
            if object_size_mb is not None:
                feature_snapshot_payload["object_size_mb"] = object_size_mb
            if last_access_days is not None:
                feature_snapshot_payload["last_access_days"] = last_access_days
            if requests_90d is not None:
                feature_snapshot_payload["requests_90d"] = requests_90d
            if access_std_dev is not None:
                feature_snapshot_payload["access_std_dev"] = access_std_dev
            if object_age_days is not None:
                feature_snapshot_payload["object_age_days"] = object_age_days
            decision_trace = {
                "formula": (
                    "confidence_final = confidence_base * data_window_factor * "
                    "billing_realism_factor * aggregation_factor * migration_risk_factor"
                ),
                "optimization_unit": optimization_unit,
                "decision_state": decision_state.value,
                "bucket_id": bucket.bucket_id if bucket else None,
                "confidence": {
                    "base": round(base_confidence, 6),
                    "final": round(confidence, 6),
                    "data_window_factor": round(decay.data_window_factor, 6),
                    "billing_realism_factor": round(decay.billing_realism_factor, 6),
                    "aggregation_factor": round(decay.aggregation_factor, 6),
                    "migration_risk_factor": round(decay.migration_risk_factor, 6),
                },
                "model_confidence": round(model_confidence, 6),
                "operational_readiness": round(operational_readiness, 6),
                "operational_readiness_band": operational_readiness_band,
                "operational_readiness_reasons": list(operational_readiness_reasons),
                "policy": {
                    "band": decay.policy_band,
                    "action": action_name,
                },
                "execution": {
                    "ingestion_mode": ingestion_mode,
                    "integration_permission": integration_permission,
                    "execution_authority": execution_authority,
                    "execution_eligibility": execution_eligibility.value,
                    "reason": execution_reason,
                    "unlock_hint": execution_unlock_hint,
                },
                "recommendation": {
                    "action": recommendation_action,
                    "state": recommendation_state,
                },
                "data_maturity": {
                    "level": data_maturity,
                    "score": round(data_maturity_score, 6),
                },
                "billing_realism": billing_realism,
                "downgrade_reasons": list(decay.downgrade_reasons),
                "pricing": pricing_trace_payload,
                "guardrails": list(guardrail_notes),
            }

            responses.append(
                RecommendationResponse(
                    id=row.id,
                    resource_name=row.resource_name,
                    bucket_id=bucket.bucket_id if bucket else None,
                    optimization_unit=optimization_unit,
                    current_tier=row.current_tier,
                    current_provider=current_provider,
                    recommended_tier=recommended_tier,
                    recommended_provider=recommended_provider,
                    estimated_monthly_savings=monthly_savings,
                    priority=row.priority
                    if decision_state == DecisionState.PREDICTED
                    else self._priority_from_risk(self._risk_level_from_confidence(confidence)),
                    status=row.status.value,
                    feature_snapshot=feature_snapshot_payload,
                    confidence_score=round(confidence, 4),
                    rule_override_trace=trace,
                    current_monthly_cost=current_monthly_cost,
                    optimized_monthly_cost=optimized_monthly_cost,
                    estimated_savings_percent=estimated_savings_percent,
                    pricing_version=pricing_version,
                    pricing_candidates=pricing_candidates,
                    cost_assumptions=cost_assumptions,
                    migration_advisory=migration_advisory,
                    bucket_metrics=bucket_metrics,
                    object_references=object_references[:50],
                    confidence_base_score=round(base_confidence, 4),
                    model_confidence=round(model_confidence, 6),
                    ml_confidence=round(model_confidence, 6),
                    data_maturity=data_maturity,
                    data_maturity_score=round(data_maturity_score, 6),
                    billing_realism=billing_realism,
                    execution_authority=execution_authority,
                    operational_readiness=round(operational_readiness, 6),
                    operational_readiness_band=operational_readiness_band,
                    operational_readiness_reasons=operational_readiness_reasons,
                    confidence_decay={
                        "data_window_factor": round(decay.data_window_factor, 6),
                        "billing_realism_factor": round(decay.billing_realism_factor, 6),
                        "aggregation_factor": round(decay.aggregation_factor, 6),
                        "migration_risk_factor": round(decay.migration_risk_factor, 6),
                    },
                    confidence_message=confidence_message,
                    decision_trace=decision_trace,
                    decision_state=decision_state.value,
                    confidence_final=round(confidence, 6),
                    confidence_trace=decision_trace["confidence"],
                    guardrail_trace=list(guardrail_notes),
                    pricing_trace=pricing_trace_payload,
                    pricing_source=pricing_trace_payload["pricing_source"],
                    pricing_confidence=pricing_confidence.value,
                    ingestion_mode=ingestion_mode,
                    integration_permission=integration_permission,
                    execution_eligibility=execution_eligibility.value,
                    execution_reason=execution_reason,
                    execution_unlock_hint=execution_unlock_hint,
                    recommendation_action=recommendation_action,
                    recommendation_state=recommendation_state,
                    migration_state=(
                        MigrationLifecycleState.BLOCKED.value
                        if recommendation_state in {"BLOCKED_BY_GUARDRAIL", "BLOCKED_BY_AUTHORITY"}
                        else MigrationLifecycleState.PLANNED.value
                    ),
                    decision_trace_block=decision_trace_block,
                    created_at=row.created_at,
                )
            )
        return responses

    def get_recommendation_summary(self, *, user_id: int, resource_id: str) -> RecommendationSummaryResponse | None:
        recommendations = self.get_recommendations(user_id=user_id)
        match = next((item for item in recommendations if item.resource_name == resource_id), None)
        if match is None:
            return None

        snapshot = match.feature_snapshot or {}
        requests_30d = self._safe_float(snapshot.get("last_30d_access_frequency"))
        requests_90d = self._safe_float(snapshot.get("requests_90d"))
        read_write_ratio = self._safe_float(snapshot.get("read_write_ratio"))
        last_access_days = self._safe_float(snapshot.get("last_access_days"), default=None)
        access_std_dev = self._safe_float(snapshot.get("access_std_dev"))
        estimated_monthly_cost = self._safe_float(snapshot.get("estimated_monthly_cost_usd"))
        object_size_mb = self._safe_float(snapshot.get("object_size_mb"), default=None)

        recency_score = math.exp(-last_access_days / 30.0) if last_access_days is not None else 0.0
        effective_access = (
            requests_30d * math.exp(-last_access_days / 30.0) if last_access_days is not None else 0.0
        )
        access_frequency = requests_30d / 30.0
        read_write_ratio = max(0.1, min(10.0, read_write_ratio))
        access_volatility = access_std_dev / (requests_30d + 1.0)
        requests_90d_value = requests_90d if requests_90d is not None else requests_30d * 3.0
        momentum_denominator = max(requests_90d_value / 3.0, 1e-6)
        momentum = requests_30d / momentum_denominator
        momentum = max(0.2, min(2.0, momentum))

        temperature_raw = (
            0.40 * math.log10(requests_30d + 1.0)
            + 0.25 * recency_score
            + 0.15 * read_write_ratio
            + 0.10 * momentum
            - 0.10 * access_volatility
        )
        temperature_score = self._normalize_temperature(temperature_raw)

        retrieval_penalty_score = self._clamp_01(estimated_monthly_cost / 200.0)
        migration_risk = self._clamp_01(
            0.4 * self._clamp_01(access_volatility) + 0.4 * recency_score + 0.2 * retrieval_penalty_score
        )

        classification = self._temperature_band(temperature_score)
        guardrail_blocked = False
        if last_access_days is not None and last_access_days < 7:
            classification = "HOT"
        if last_access_days is not None and last_access_days < 30 and classification == "ARCHIVE":
            classification = "COLD"
            guardrail_blocked = True
        if requests_30d > 200 and classification == "ARCHIVE":
            classification = "COLD"
            guardrail_blocked = True

        retrieval_penalty_high = False
        if object_size_mb is not None:
            object_size_tb = (object_size_mb / 1024.0) / 1024.0
            retrieval_penalty_high = object_size_tb > 5.0 and retrieval_penalty_score >= 1.0
        if retrieval_penalty_high and classification == "ARCHIVE":
            classification = "COLD"
            guardrail_blocked = True

        lifecycle_stage = "UNKNOWN"
        if last_access_days is not None:
            lifecycle_stage = self._lifecycle_tier(last_access_days=int(last_access_days))

        final_tier = classification
        if lifecycle_stage != "UNKNOWN":
            final_tier = self._coldest_tier(final_tier, lifecycle_stage)
        if guardrail_blocked and final_tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            final_tier = "COLD"

        predicted_archive_in_days = None
        if last_access_days is not None:
            predicted_archive_in_days = max(180 - int(round(last_access_days)), 0)

        reasoning: list[str] = []
        if last_access_days is not None:
            reasoning.append(f"Last access occurred {int(round(last_access_days))} days ago.")
        if momentum < 0.6:
            reasoning.append("Access frequency has declined.")
            reasoning.append("Momentum indicates cooling workload.")
        elif momentum > 1.2:
            reasoning.append("Access frequency is increasing.")
            reasoning.append("Momentum indicates heating workload.")
        else:
            reasoning.append("Access frequency is stable.")
            reasoning.append("Momentum indicates stable workload.")
        reasoning.append(f"Temperature score classified object as {final_tier}.")
        if lifecycle_stage != "UNKNOWN":
            if lifecycle_stage == final_tier:
                reasoning.append(f"Lifecycle cooling stage confirms transition to {lifecycle_stage} tier.")
            else:
                reasoning.append(f"Lifecycle cooling stage suggests {lifecycle_stage} tier.")
        if match.estimated_monthly_savings > 0:
            reasoning.append(
                f"{match.recommended_tier} reduces storage cost by ${match.estimated_monthly_savings:.2f}/mo."
            )

        current_cost = match.current_monthly_cost if match.current_monthly_cost is not None else estimated_monthly_cost
        recommended_cost = match.optimized_monthly_cost
        if recommended_cost is None and current_cost is not None:
            recommended_cost = max(current_cost - match.estimated_monthly_savings, 0.0)

        if migration_risk >= 0.6:
            risk_band = "HIGH"
        elif migration_risk >= 0.3:
            risk_band = "MEDIUM"
        else:
            risk_band = "LOW"

        return RecommendationSummaryResponse(
            resource_id=match.resource_name,
            provider=match.current_provider,
            current_tier=match.current_tier,
            recommended_tier=match.recommended_tier,
            classification=final_tier,
            lifecycle_stage=lifecycle_stage,
            temperature_score=round(temperature_score, 4),
            recency_score=round(recency_score, 4),
            momentum=round(momentum, 4),
            access_volatility=round(access_volatility, 4),
            access_frequency=round(access_frequency, 4),
            effective_access=round(effective_access, 4),
            requests_30d=round(requests_30d, 2),
            requests_90d=round(requests_90d_value, 2),
            last_access_days=int(round(last_access_days)) if last_access_days is not None else None,
            storage_cost_current=round(current_cost, 4) if current_cost is not None else None,
            storage_cost_recommended=round(recommended_cost, 4) if recommended_cost is not None else None,
            estimated_savings=round(match.estimated_monthly_savings, 4),
            migration_risk=risk_band,
            migration_risk_score=round(migration_risk, 4),
            confidence=round(match.confidence_final, 4),
            execution_eligibility=match.execution_eligibility,
            predicted_archive_in_days=predicted_archive_in_days,
            reasoning=reasoning,
        )

    def get_grouped_recommendations(self, user_id: int) -> list[GroupedRecommendationResponse]:
        items = self.get_recommendations(user_id=user_id)
        grouped: dict[tuple[str, str, str, str | None], dict[str, float | str | int | list[str]]] = {}

        for item in items:
            data_temperature = str(item.feature_snapshot.get("temperature", "UNKNOWN"))
            key = (data_temperature, item.recommended_provider, item.recommended_tier, item.pricing_version)
            if key not in grouped:
                grouped[key] = {
                    "dataset_count": 0,
                    "total_monthly_savings": 0.0,
                    "total_confidence": 0.0,
                    "preview_resource_names": [],
                }

            bucket = grouped[key]
            bucket["dataset_count"] = int(bucket["dataset_count"]) + 1
            bucket["total_monthly_savings"] = float(bucket["total_monthly_savings"]) + float(item.estimated_monthly_savings)
            bucket["total_confidence"] = float(bucket["total_confidence"]) + float(item.confidence_score)
            previews = bucket["preview_resource_names"]
            if isinstance(previews, list) and len(previews) < 10:
                previews.append(item.resource_name)

        responses: list[GroupedRecommendationResponse] = []
        for (data_temperature, provider, tier, pricing_version), bucket in grouped.items():
            dataset_count = int(bucket["dataset_count"])
            total_savings = round(float(bucket["total_monthly_savings"]), 4)
            avg_savings = round(total_savings / max(dataset_count, 1), 4)
            avg_confidence = round(float(bucket["total_confidence"]) / max(dataset_count, 1), 4)
            risk_level = self._risk_level_from_confidence(avg_confidence)
            group_key = f"{data_temperature}:{provider}:{tier}:{pricing_version or 'none'}"

            responses.append(
                GroupedRecommendationResponse(
                    group_key=group_key,
                    data_temperature=data_temperature,
                    recommended_provider=provider,
                    recommended_tier=tier,
                    dataset_count=dataset_count,
                    avg_monthly_savings=avg_savings,
                    total_monthly_savings=total_savings,
                    avg_confidence_score=avg_confidence,
                    risk_level=risk_level,
                    pricing_version=pricing_version,
                    preview_resource_names=list(bucket["preview_resource_names"]) if isinstance(bucket["preview_resource_names"], list) else [],
                )
            )

        responses.sort(key=lambda item: item.total_monthly_savings, reverse=True)
        return responses

    def get_data_temperature(self, user_id: int) -> DataTemperatureResponse:
        bucket_grouped = self.db.execute(
            select(BucketAggregate.temperature, func.count(BucketAggregate.id))
            .where(BucketAggregate.user_id == user_id)
            .group_by(BucketAggregate.temperature)
        ).all()
        grouped = bucket_grouped
        if not grouped:
            grouped = self.db.execute(
                select(StorageRecord.temperature, func.count(StorageRecord.id))
                .where(StorageRecord.user_id == user_id)
                .group_by(StorageRecord.temperature)
            ).all()

        mapped = defaultdict(int)
        for temp, count in grouped:
            mapped[temp] = int(count)

        return DataTemperatureResponse(
            hot_count=mapped[DataTemperature.HOT],
            cold_count=mapped[DataTemperature.COLD],
            archive_count=mapped[DataTemperature.ARCHIVE],
        )

    def get_user_migrations(self, user_id: int) -> list[UserMigrationResponse]:
        rows = self.db.scalars(
            select(MigrationJob)
            .where(MigrationJob.user_id == user_id)
            .order_by(desc(MigrationJob.created_at))
            .limit(100)
        ).all()
        resource_names = {row.resource_name for row in rows}
        storage_by_resource = self._latest_storage_by_resource(user_id=user_id, resource_names=resource_names)
        recommendation_by_resource = self._latest_recommendation_by_resource(
            user_id=user_id,
            resource_names=resource_names,
        )

        response: list[UserMigrationResponse] = []
        for row in rows:
            storage = storage_by_resource.get(row.resource_name)
            recommendation = recommendation_by_resource.get(row.resource_name)

            before_cost = float(storage.storage_cost) if storage else max((recommendation.estimated_monthly_savings if recommendation else 5.0) * 2.0, 5.0)
            after_cost = (
                max(before_cost - float(recommendation.estimated_monthly_savings), 0.0)
                if recommendation
                else round(before_cost * 0.78, 2)
            )
            cost_delta = round(before_cost - after_cost, 2)

            risk_base = {
                "PENDING": 0.38,
                "RUNNING": 0.46,
                "COMPLETED": 0.22,
                "FAILED": 0.88,
            }.get(row.status.value, 0.5)
            cross_cloud_penalty = 0.06 if row.source_provider != row.target_provider else 0.0
            error_penalty = 0.1 if row.error_message else 0.0
            progress_penalty = 0.08 if row.progress_percent < 50 and row.status.value == "RUNNING" else 0.0
            risk_score = min(1.0, round(risk_base + cross_cloud_penalty + error_penalty + progress_penalty, 3))

            rollback_plan = (
                f"Retain source snapshot on {row.source_provider.value}; if validation fails, "
                f"copy objects back from {row.target_provider.value} to {row.source_provider.value}, "
                "re-point read traffic, and re-run checksum validation."
            )

            response.append(
                UserMigrationResponse(
                    id=row.id,
                    resource_name=row.resource_name,
                    source_provider=row.source_provider.value,
                    target_provider=row.target_provider.value,
                    status=row.status.value,
                    progress_percent=row.progress_percent,
                    before_monthly_cost=round(before_cost, 2),
                    after_monthly_cost=round(after_cost, 2),
                    cost_delta=cost_delta,
                    risk_score=risk_score,
                    rollback_plan=rollback_plan,
                    migration_state=self._lifecycle_state_from_job_status(status=row.status.value),
                    error_message=row.error_message,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    created_at=row.created_at,
                )
            )
        return response

    def _latest_bucket_by_bucket_id(self, *, user_id: int) -> dict[str, BucketAggregate]:
        rows = self.db.scalars(
            select(BucketAggregate)
            .where(BucketAggregate.user_id == user_id)
            .order_by(asc(BucketAggregate.bucket_id), desc(BucketAggregate.updated_at), desc(BucketAggregate.id))
        ).all()
        latest: dict[str, BucketAggregate] = {}
        for row in rows:
            latest.setdefault(row.bucket_id, row)
        return latest

    def _bucket_for_resource(self, *, user_id: int, resource_name: str) -> BucketAggregate | None:
        ref = self.db.scalar(
            select(BucketObjectReference)
            .where(
                BucketObjectReference.user_id == user_id,
                BucketObjectReference.resource_name == resource_name,
            )
            .order_by(desc(BucketObjectReference.last_observed_at), desc(BucketObjectReference.id))
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

    def _latest_storage_by_resource(self, *, user_id: int, resource_names: set[str]) -> dict[str, StorageRecord]:
        if not resource_names:
            return {}
        rows = self.db.scalars(
            select(StorageRecord)
            .where(StorageRecord.user_id == user_id, StorageRecord.resource_name.in_(resource_names))
            .order_by(asc(StorageRecord.resource_name), desc(StorageRecord.updated_at), desc(StorageRecord.id))
        ).all()
        latest: dict[str, StorageRecord] = {}
        for row in rows:
            latest.setdefault(row.resource_name, row)
        return latest

    def _latest_feature_snapshot_by_resource(
        self,
        *,
        user_id: int,
        resource_names: set[str],
    ) -> dict[str, dict[str, float]]:
        if not resource_names:
            return {}

        # Recent-first bounded scan keeps the query cheap while preserving per-resource fidelity.
        scan_limit = max(400, len(resource_names) * 40)
        rows = self.db.scalars(
            select(IngestedRecord)
            .where(IngestedRecord.user_id == user_id)
            .order_by(desc(IngestedRecord.created_at), desc(IngestedRecord.id))
            .limit(scan_limit)
        ).all()

        latest: dict[str, dict[str, float]] = {}
        for row in rows:
            raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
            record_payload = raw_payload.get("record") if isinstance(raw_payload.get("record"), dict) else raw_payload
            if not isinstance(record_payload, dict):
                continue
            resource_name = self._resolve_resource_name(record_payload=record_payload, external_id=row.external_id)
            if resource_name not in resource_names or resource_name in latest:
                continue
            latest[resource_name] = self._extract_feature_snapshot(record_payload=record_payload)
            if len(latest) == len(resource_names):
                break
        return latest

    def _resolve_resource_name(self, *, record_payload: dict[str, Any], external_id: str | None) -> str:
        candidates = (
            record_payload.get("resource_name"),
            record_payload.get("resource_id"),
            record_payload.get("file_name"),
            record_payload.get("file_id"),
            record_payload.get("object_key"),
            record_payload.get("object_name"),
            record_payload.get("id"),
            record_payload.get("name"),
            external_id,
        )
        for candidate in candidates:
            if candidate is None:
                continue
            text = str(candidate).strip()
            if text:
                return text
        return ""

    def _extract_feature_snapshot(self, *, record_payload: dict[str, Any]) -> dict[str, float]:
        access_frequency = self._first_numeric(
            record_payload,
            paths=[
                ("requests_30d",),
                ("access_frequency_30d",),
                ("read_count_30d",),
                ("access_count",),
                ("usage_metrics", "requests_30d"),
                ("usage_metrics", "access_frequency_30d"),
                ("usage_metrics", "read_count_30d"),
                ("usage_metrics", "access_count"),
            ],
        )
        object_size_mb = self._first_numeric(
            record_payload,
            paths=[
                ("size_mb",),
                ("object_size_mb",),
                ("file_size_mb",),
                ("size",),
                ("object_size",),
            ],
        )
        if object_size_mb is None or object_size_mb <= 0:
            size_bytes = self._first_numeric(
                record_payload,
                paths=[
                    ("size_bytes",),
                    ("object_size_bytes",),
                    ("file_size_bytes",),
                    ("bytes",),
                ],
            )
            if size_bytes is not None and size_bytes > 0:
                object_size_mb = size_bytes / (1024.0 * 1024.0)
        read_write_ratio = self._first_numeric(
            record_payload,
            paths=[
                ("read_write_ratio",),
                ("usage_metrics", "read_write_ratio"),
                ("metrics", "read_write_ratio"),
            ],
        )
        last_access_days = self._first_numeric(
            record_payload,
            paths=[
                ("last_access_days",),
                ("usage_metrics", "last_access_days"),
                ("metrics", "last_access_days"),
            ],
        )
        requests_90d = self._first_numeric(
            record_payload,
            paths=[
                ("requests_90d",),
                ("access_frequency_90d",),
                ("usage_metrics", "requests_90d"),
                ("usage_metrics", "access_frequency_90d"),
            ],
        )
        access_std_dev = self._first_numeric(
            record_payload,
            paths=[
                ("access_std_dev",),
                ("access_variance",),
                ("usage_metrics", "access_std_dev"),
            ],
        )
        object_age_days = self._first_numeric(
            record_payload,
            paths=[
                ("object_age_days",),
                ("age_days",),
                ("usage_metrics", "object_age_days"),
            ],
        )
        snapshot: dict[str, float] = {}
        if access_frequency is not None:
            snapshot["last_30d_access_frequency"] = max(access_frequency, 0.0)
        if object_size_mb is not None and object_size_mb > 0:
            snapshot["object_size_mb"] = object_size_mb
        if read_write_ratio is not None:
            snapshot["read_write_ratio"] = max(read_write_ratio, 0.0)
        if last_access_days is not None:
            snapshot["last_access_days"] = max(last_access_days, 0.0)
        if requests_90d is not None:
            snapshot["requests_90d"] = max(requests_90d, 0.0)
        if access_std_dev is not None:
            snapshot["access_std_dev"] = max(access_std_dev, 0.0)
        if object_age_days is not None:
            snapshot["object_age_days"] = max(object_age_days, 0.0)
        return snapshot

    def _first_numeric(self, payload: dict[str, Any], *, paths: list[tuple[str, ...]]) -> float | None:
        for path in paths:
            value = self._nested_value(payload, path)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric != numeric:  # NaN guard
                continue
            return numeric
        return None

    def _nested_value(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _latest_recommendation_by_resource(
        self,
        *,
        user_id: int,
        resource_names: set[str],
    ) -> dict[str, Recommendation]:
        if not resource_names:
            return {}
        rows = self.db.scalars(
            select(Recommendation)
            .where(Recommendation.user_id == user_id, Recommendation.resource_name.in_(resource_names))
            .order_by(asc(Recommendation.resource_name), desc(Recommendation.created_at), desc(Recommendation.id))
        ).all()
        latest: dict[str, Recommendation] = {}
        for row in rows:
            latest.setdefault(row.resource_name, row)
        return latest

    def _latest_ingestion_job(self, *, user_id: int) -> IngestionJob | None:
        return self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.user_id == user_id)
            .order_by(desc(IngestionJob.created_at), desc(IngestionJob.id))
            .limit(1)
        )

    def _dataset_label(self, job: IngestionJob) -> str:
        base = Path(job.file_name).stem if job.file_name else "Upload"
        if not base:
            base = "Upload"
        return f"{base}_{job.created_at:%Y_%m_%d}"

    def _dataset_source_label(self, job: IngestionJob) -> str:
        origin = str(job.data_origin or "").upper()
        if origin == "USER_UPLOAD":
            return "File Upload"
        if origin == "API":
            return "API"
        if origin == "CLOUD_INTEGRATION":
            return "Cloud Integration"
        if origin == "PUBLIC_DATASET":
            return "Public Dataset"
        return origin.replace("_", " ").title() if origin else "Unknown"

    def _confidence_band(self, *, confidence: float) -> str:
        if confidence > 0.80:
            return "High"
        if confidence >= 0.50:
            return "Medium"
        return "Low"

    def _is_archive_tier(self, tier: str) -> bool:
        tier_normalized = str(tier or "").strip().lower()
        return any(token in tier_normalized for token in ("archive", "glacier", "deep"))

    def _safe_hot_tier(self, provider: str) -> str:
        provider_upper = str(provider or "").upper()
        if provider_upper == "AZURE":
            return "Hot Blob"
        if provider_upper == "GCP":
            return "Standard"
        return "S3 Standard"

    def apply_latency_guardrail(
        self,
        ml_prediction: str,
        access_count_30d: float,
        current_provider: str,
    ) -> str:
        predicted_provider, predicted_tier = self._parse_ml_prediction(
            ml_prediction=ml_prediction,
            current_provider=current_provider,
        )
        access = max(float(access_count_30d), 0.0)
        current_provider_upper = str(current_provider or "").upper()

        # Rule 2: high-access cross-cloud moves are blocked to avoid egress-heavy outcomes.
        if predicted_provider != current_provider_upper and access > 10:
            return "STAY_IN_CURRENT_PROVIDER"

        # Rule 1: high-access archive classes are downgraded to safer infrequent-access tiers.
        if self._is_archive_tier(predicted_tier) and access > 4:
            return self._conservative_tier(predicted_provider)

        return predicted_tier

    def _parse_ml_prediction(self, *, ml_prediction: str, current_provider: str) -> tuple[str, str]:
        provider = str(current_provider or "").upper()
        tier = str(ml_prediction or "").strip()
        if ":" in tier:
            maybe_provider, maybe_tier = tier.split(":", 1)
            provider_candidate = maybe_provider.strip().upper()
            if provider_candidate in {"AWS", "AZURE", "GCP", "MULTI"}:
                provider = provider_candidate
            tier = maybe_tier.strip()
        return provider, tier

    def _conservative_tier(self, provider: str) -> str:
        provider_upper = str(provider or "").upper()
        if provider_upper == "AZURE":
            return "Cool Blob"
        if provider_upper == "GCP":
            return "Nearline"
        return "Standard-IA"

    def _archive_tier(self, provider: str) -> str:
        provider_upper = str(provider or "").upper()
        if provider_upper == "AZURE":
            return "Archive Blob"
        if provider_upper == "GCP":
            return "Archive"
        return "Glacier"

    def _find_candidate_monthly_cost(
        self,
        *,
        candidates: list,
        provider: str,
        tier: str,
    ) -> float | None:
        provider_upper = str(provider or "").upper()
        tier_normalized = str(tier or "").strip().lower()
        for candidate in candidates:
            cloud = str(getattr(candidate, "cloud", "")).upper()
            native_tier = str(getattr(candidate, "native_tier", "")).strip().lower()
            if cloud == provider_upper and native_tier == tier_normalized:
                return float(getattr(candidate, "monthly_cost", 0.0))
        return None

    def _fallback_rate_for_tier(self, tier: str) -> float | None:
        normalized = str(tier or "").strip().lower().replace("_", "").replace("-", "").replace(" ", "")
        rates = {
            "standard": 0.023,
            "s3standard": 0.023,
            "hotblob": 0.023,
            "standardia": 0.0125,
            "s3standardia": 0.0125,
            "onezoneia": 0.0125,
            "nearline": 0.0125,
            "coolblob": 0.0028,
            "archive": 0.00099,
            "archiveblob": 0.00099,
            "glacier": 0.00099,
            "deeparchive": 0.00099,
        }
        return rates.get(normalized)

    def _risk_level_from_confidence(self, confidence: float) -> str:
        if confidence > 0.80:
            return "LOW"
        if confidence >= 0.50:
            return "MEDIUM"
        return "HIGH"

    def _lifecycle_state_from_job_status(self, *, status: str) -> str:
        normalized = str(status or "").upper()
        mapping = {
            "PENDING": MigrationLifecycleState.PLANNED.value,
            "RUNNING": MigrationLifecycleState.EXECUTING.value,
            "COMPLETED": MigrationLifecycleState.COMPLETED.value,
            "FAILED": MigrationLifecycleState.BLOCKED.value,
        }
        return mapping.get(normalized, MigrationLifecycleState.PLANNED.value)

    def _priority_from_risk(self, risk_level: str) -> str:
        mapping = {
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
        }
        return mapping.get(str(risk_level).upper(), "MEDIUM")

    def _pricing_confidence(
        self,
        *,
        has_real_billing: bool,
        pricing_version: str | None,
    ) -> PricingConfidence:
        if has_real_billing:
            return PricingConfidence.REAL
        if pricing_version:
            return PricingConfidence.EXPORT
        return PricingConfidence.ESTIMATE

    def _integration_authority_by_provider(self, *, user_id: int) -> dict[str, tuple[str, str]]:
        rows = self.db.scalars(
            select(DataSource)
            .where(
                DataSource.user_id == user_id,
                DataSource.source_type == DataSourceType.OFFICIAL_API,
                DataSource.status == "ACTIVE",
            )
            .order_by(desc(DataSource.last_synced_at), desc(DataSource.updated_at), desc(DataSource.id))
        ).all()

        authority: dict[str, tuple[str, str]] = {}
        for row in rows:
            provider = str(row.provider or "").upper()
            if not provider or provider in authority:
                continue
            auth_config = row.auth_config if isinstance(row.auth_config, dict) else {}
            is_read_only = bool(auth_config.get("is_read_only", True))
            permission = "READ_ONLY" if is_read_only else "READ_WRITE"
            authority[provider] = ("CLOUD_INTEGRATION", permission)
        return authority

    def _derive_execution_eligibility(
        self,
        *,
        execution_authority: str,
        hard_block: bool,
        is_cross_cloud: bool,
    ) -> tuple[ExecutionEligibility, str]:
        if hard_block:
            return ExecutionEligibility.NONE, "Blocked by hard guardrail."
        authority = str(execution_authority).upper()
        if authority == "WRITE_ENABLED":
            if is_cross_cloud:
                return (
                    ExecutionEligibility.DRY_RUN_ELIGIBLE,
                    "Cross-cloud change can be simulated in dry-run only; direct execution is disabled.",
                )
            return ExecutionEligibility.EXECUTABLE, "Write authority verified. Execution can proceed via dry-run gate."
        if authority == "DRY_RUN_ONLY":
            return (
                ExecutionEligibility.DRY_RUN_ELIGIBLE,
                "Dry-run is available. Connect write-enabled integration to execute migration.",
            )
        return ExecutionEligibility.NONE, "Execution authority unavailable for this provider."

    def _derive_execution_authority(
        self,
        *,
        ingestion_mode: str,
        integration_permission: str,
    ) -> str:
        ingestion = str(ingestion_mode).upper()
        permission = str(integration_permission).upper()
        if ingestion == "CLOUD_INTEGRATION" and permission == "READ_WRITE":
            return "WRITE_ENABLED"
        if ingestion in {"CLOUD_INTEGRATION", "API_INGESTION", "USER_UPLOAD", "USER_SUBMITTED"}:
            return "DRY_RUN_ONLY"
        return "NONE"

    def _billing_realism(self, *, pricing_confidence: PricingConfidence) -> str:
        if pricing_confidence == PricingConfidence.REAL:
            return "LIVE"
        if pricing_confidence == PricingConfidence.EXPORT:
            return "EXPORT"
        return "ESTIMATE"

    def _derive_data_maturity(
        self,
        *,
        ingestion_mode: str,
        observation_days: int,
        object_count: int,
        total_size_gb: float,
        billing_realism: str,
    ) -> tuple[str, float]:
        days = max(int(observation_days), 1)
        realistic_density = object_count >= 30 and total_size_gb >= 1.0
        ingestion = str(ingestion_mode).upper()
        realism = str(billing_realism).upper()

        if ingestion == "CLOUD_INTEGRATION" and realism == "LIVE" and days >= 30:
            return "LIVE_MATURE", 1.0
        if realism in {"EXPORT", "LIVE"} and days >= 14:
            return "EXPORT_MATURE", 0.82
        if realistic_density or days >= 2:
            return "SYNTHETIC_MATURE", 0.62
        return "SYNTHETIC_MATURE", 0.45

    @staticmethod
    def _clamp_01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _normalize_temperature(raw_score: float) -> float:
        if raw_score <= 0:
            return 0.0
        normalized = (float(raw_score) / 3.0) * 10.0
        return max(0.0, min(10.0, normalized))

    @staticmethod
    def _temperature_band(score: float) -> str:
        """Map a 0-10 temperature score into a storage band."""
        value = float(score)
        if value >= 7.5:
            return "HOT"
        if value >= 5.0:
            return "WARM"
        if value >= 3.0:
            return "COLD"
        return "ARCHIVE"

    @staticmethod
    def _lifecycle_tier(*, last_access_days: int) -> str:
        """Derive lifecycle tier from access recency."""
        days = max(int(last_access_days), 0)
        if days < 30:
            return "HOT"
        if days < 90:
            return "WARM"
        if days < 180:
            return "COLD"
        return "ARCHIVE"

    @staticmethod
    def _coldest_tier(primary: str, secondary: str) -> str:
        """Return the colder of two tiers."""
        order = {
            "HOT": 0,
            "WARM": 1,
            "COOL": 2,
            "COLD": 2,
            "STANDARD_IA": 2,
            "ARCHIVE": 3,
            "DEEP_ARCHIVE": 4,
        }
        first = order.get(str(primary).upper(), -1)
        second = order.get(str(secondary).upper(), -1)
        if first == -1 and second == -1:
            return primary
        if second > first:
            return secondary
        return primary

    @staticmethod
    def _safe_float(value: Any, *, default: float | None = 0.0) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return default

    def _operational_readiness_score(
        self,
        *,
        data_window_factor: float,
        billing_realism_factor: float,
        aggregation_factor: float,
        data_maturity_score: float,
    ) -> float:
        score = (
            float(data_window_factor)
            * float(billing_realism_factor)
            * float(aggregation_factor)
            * float(data_maturity_score)
        )
        return round(self._clamp_01(score), 6)

    def _operational_readiness_band(self, score: float) -> str:
        if score >= 0.80:
            return "READY"
        if score >= 0.50:
            return "CONDITIONAL"
        return "LOW_MATURITY"

    def _operational_readiness_reasons(
        self,
        *,
        data_window_factor: float,
        billing_realism_factor: float,
        aggregation_factor: float,
        data_maturity: str,
        billing_realism: str,
    ) -> list[str]:
        reasons: list[str] = []
        reasons.append(f"Data maturity: {data_maturity}.")
        reasons.append(f"Billing realism: {billing_realism}.")
        if float(data_window_factor) < 1.0:
            reasons.append("Observation window is limited.")
        if float(billing_realism_factor) < 1.0:
            reasons.append("Pricing is estimate-based or export-based, not fully real-billing.")
        if float(aggregation_factor) < 1.0:
            reasons.append("Decision is based on lower-fidelity object-level aggregation.")
        if not reasons:
            reasons.append("Operational data maturity checks passed.")
        return reasons

    def _execution_unlock_hint(
        self,
        *,
        ingestion_mode: str,
        integration_permission: str,
        execution_authority: str,
        execution_eligibility: ExecutionEligibility,
        hard_block: bool,
    ) -> str:
        if hard_block:
            return "Resolve guardrail constraints before any migration activity."
        if execution_eligibility == ExecutionEligibility.EXECUTABLE:
            return "Run migration with mandatory dry-run and approval policy."
        if execution_eligibility == ExecutionEligibility.DRY_RUN_ELIGIBLE:
            if str(execution_authority).upper() == "WRITE_ENABLED":
                return "Dry-run is available now; direct execution is limited by policy scope."
            return "Connect cloud integration with READ_WRITE permissions to enable direct execution."
        source = str(ingestion_mode).upper() or "UNKNOWN"
        perm = str(integration_permission).upper() or "NONE"
        return f"Execution blocked because source={source}, permission={perm}. Required: cloud write integration or dry-run authority."

    def _apply_pricing_clamp(
        self,
        *,
        decision_state: DecisionState,
        before_cost: float | None,
        after_cost: float | None,
    ) -> tuple[float, float, float, float | None]:
        before = round(max(float(before_cost or 0.0), 0.0), 4)
        if decision_state != DecisionState.PREDICTED:
            # Fallback/blocked/no-op actions are safety actions and cannot claim exploratory savings.
            return before, before, 0.0, None

        after = round(max(float(after_cost if after_cost is not None else before), 0.0), 4)
        if after > before:
            after = before
        savings = round(max(before - after, 0.0), 4)
        percent = round((savings / before) * 100, 2) if before > 0 else None
        return before, after, savings, percent

    def _retrieval_ratio_for_temp(self, data_temperature: DataTemperature) -> float:
        return {
            DataTemperature.HOT: 0.18,
            DataTemperature.COLD: 0.06,
            DataTemperature.ARCHIVE: 0.01,
        }[data_temperature]

    def _estimate_storage_gb_from_cost(self, *, data_temperature: DataTemperature, monthly_cost: float) -> float:
        baseline_rate = {
            DataTemperature.HOT: 0.023,
            DataTemperature.COLD: 0.0125,
            DataTemperature.ARCHIVE: 0.004,
        }[data_temperature]
        return max(float(monthly_cost) / baseline_rate, 1.0)

    def _build_migration_advisory(
        self,
        *,
        current_provider: str,
        recommended_provider: str,
        recommended_tier: str,
        confidence: float,
        storage_gb: float,
        decision_state: DecisionState,
        pricing_confidence: PricingConfidence,
        execution_eligibility: ExecutionEligibility,
        execution_reason: str,
    ) -> dict[str, Any]:
        provider_upper = str(recommended_provider or "").upper()
        tool = {
            "AZURE": "AzCopy",
            "GCP": "Storage Transfer Service",
            "AWS": "AWS DataSync",
        }.get(provider_upper, "rclone")

        strategy = "offline_migration" if current_provider.upper() != provider_upper else "in_place_tier_transition"
        estimated_time_hours = round(min(72.0, max(0.5, storage_gb / 220.0)), 2)
        lifecycle_path = [
            MigrationLifecycleState.PLANNED.value,
            MigrationLifecycleState.APPROVED.value,
            MigrationLifecycleState.DRY_RUN.value,
            MigrationLifecycleState.EXECUTING.value,
            MigrationLifecycleState.COMPLETED.value,
            MigrationLifecycleState.ROLLED_BACK.value,
            MigrationLifecycleState.BLOCKED.value,
        ]
        execution_allowed = execution_eligibility == ExecutionEligibility.EXECUTABLE
        lifecycle_state = (
            MigrationLifecycleState.PLANNED.value
            if execution_eligibility in (ExecutionEligibility.EXECUTABLE, ExecutionEligibility.DRY_RUN_ELIGIBLE)
            else MigrationLifecycleState.BLOCKED.value
        )
        transition_rules = {
            "APPROVE": "PLANNED -> APPROVED",
            "DRY_RUN": "APPROVED -> DRY_RUN",
            "EXECUTE": "APPROVED -> EXECUTING",
            "COMPLETE": "EXECUTING -> COMPLETED",
            "ROLLBACK": "EXECUTING|COMPLETED -> ROLLED_BACK",
            "BLOCK": "ANY_NON_TERMINAL -> BLOCKED",
        }

        return {
            "strategy": strategy,
            "tool": tool,
            "downtime_required": False,
            "estimated_time_hours": estimated_time_hours,
            "risk_level": self._risk_level_from_confidence(confidence),
            "lifecycle_state": lifecycle_state,
            "lifecycle_path": lifecycle_path,
            "execution_allowed": execution_allowed,
            "execution_eligibility": execution_eligibility.value,
            "block_reason": (
                execution_reason
                if execution_eligibility == ExecutionEligibility.NONE
                else (
                    "Dry-run is available. Direct execution requires write-enabled integration and approvals."
                    if execution_eligibility == ExecutionEligibility.DRY_RUN_ELIGIBLE
                    else ""
                )
            ),
            "transition_rules": transition_rules,
            "steps": [
                "Create target bucket/container and validate region placement.",
                "Assign least-privilege IAM/RBAC permissions for migration service principal.",
                f"Run {tool} in dry-run mode and validate object inventory.",
                "Execute migration with checksum/integrity verification.",
                "Switch application endpoint and monitor read/write latency.",
                f"Enable lifecycle rules and retention policy for {recommended_tier}.",
            ],
        }
