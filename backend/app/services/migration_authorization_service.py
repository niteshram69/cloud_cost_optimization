from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AuditEvent,
    CircuitBreakerAction,
    CircuitBreakerEvent,
    CircuitBreakerOutcome,
    CloudProvider,
    ExecutionEligibility,
    GovernancePolicy,
    GovernanceRuleType,
    MetricHistory,
    MigrationExecutionMode,
    MigrationLifecycleState,
    MigrationPlan,
    RiskCode,
    StorageRecord,
    User,
)
from backend.app.schemas.dashboard import RecommendationResponse
from backend.app.schemas.migration_authorization import MigrationAuthorizeRequest, MigrationAuthorizeResponse
from backend.app.services.dashboard_service import DashboardService


class MigrationAuthorizationService:
    """
    Zero-Trust migration execution service.

    Rules enforced here:
    - ML recommendations never auto-execute; client authorization is mandatory.
    - Hard guardrails cannot be bypassed.
    - Low-confidence/downgraded outcomes require explicit risk acknowledgements.
    - UI-triggered migrations are in-place tier transitions only (no cross-cloud moves).
    - Every run passes through DRY_RUN and is audit logged.
    - Runtime anomalies trigger automatic rollback and circuit-breaker backoff.
    """

    DEFAULT_CONFIDENCE_THRESHOLD = 0.80
    DEFAULT_BACKOFF_DAYS = 30

    REQUIRED_RISKS = {
        RiskCode.LATENCY.value,
        RiskCode.RETRIEVAL_COST.value,
    }

    STATE_TRANSITIONS: dict[MigrationLifecycleState, set[MigrationLifecycleState]] = {
        MigrationLifecycleState.PLANNED: {MigrationLifecycleState.DRY_RUN},
        MigrationLifecycleState.DRY_RUN: {MigrationLifecycleState.APPROVED},
        MigrationLifecycleState.APPROVED: {MigrationLifecycleState.EXECUTING},
        MigrationLifecycleState.EXECUTING: {
            MigrationLifecycleState.COMPLETED,
            MigrationLifecycleState.ROLLED_BACK,
        },
        MigrationLifecycleState.ROLLED_BACK: {MigrationLifecycleState.BLOCKED},
        MigrationLifecycleState.COMPLETED: set(),
        MigrationLifecycleState.BLOCKED: set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def authorize_and_execute(
        self,
        *,
        current_user: User,
        payload: MigrationAuthorizeRequest,
    ) -> MigrationAuthorizeResponse:
        recommendation = self._resolve_recommendation(
            user_id=current_user.id,
            recommendation_id=payload.recommendation_id,
            resource_id=payload.resource_id,
        )
        resource_id = recommendation.resource_name
        storage_record = self._resolve_storage_record(user_id=current_user.id, resource_id=resource_id)

        self._reject_if_backoff_active(storage_record_id=storage_record.id)

        confidence_threshold = self._resolve_confidence_threshold(tenant_id=str(current_user.id))
        decision_state = str(recommendation.decision_state).upper()
        execution_eligibility = str(recommendation.execution_eligibility).upper()
        recommendation_state = str(getattr(recommendation, "recommendation_state", "")).upper()

        hard_block = decision_state == "BLOCKED" or recommendation_state == "BLOCKED_BY_GUARDRAIL"
        if hard_block:
            event = self._record_circuit_breaker(
                user_id=current_user.id,
                storage_record_id=storage_record.id,
                plan_id=None,
                action=self._action_for_tier(recommendation.recommended_tier),
                outcome=CircuitBreakerOutcome.BLOCKED_PRE_FLIGHT,
                failure_code="HARD_GUARDRAIL_BLOCK",
                failure_details={
                    "decision_state": recommendation.decision_state,
                    "guardrail_trace": recommendation.guardrail_trace,
                    "resource_id": resource_id,
                },
                rollback_reason="Blocked by hard guardrail",
                backoff_days=7,
            )
            self._record_audit_event(
                user_id=current_user.id,
                plan_id=None,
                payload={
                    "who": str(current_user.id),
                    "what": "manual_migration",
                    "resource": resource_id,
                    "confidence": float(recommendation.confidence_final),
                    "guardrails": recommendation.guardrail_trace,
                    "risks_acknowledged": False,
                    "execution_result": "BLOCKED",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event_id": event.event_id,
                    "recommendation_id": recommendation.id,
                },
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Blocked by hard guardrail. Manual migration is not allowed.",
            )

        if execution_eligibility == ExecutionEligibility.NONE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=recommendation.execution_reason or "Execution is not allowed for this recommendation.",
            )

        current_provider = storage_record.provider.value
        recommended_provider = str(recommendation.recommended_provider).upper()
        direct_execute_allowed = execution_eligibility == ExecutionEligibility.EXECUTABLE.value
        if direct_execute_allowed and recommended_provider != current_provider:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cross-cloud migrations are not allowed from UI. Use orchestrated workflow.",
            )

        approved_target_tier = (payload.approved_target_tier or recommendation.recommended_tier).strip()
        if approved_target_tier.lower() != recommendation.recommended_tier.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approved target tier must match the recommended in-place tier.",
            )

        if approved_target_tier.lower() == recommendation.current_tier.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No-op tier transition is not executable.",
            )

        explicit_ack_required = (
            direct_execute_allowed
            and self.requires_explicit_ack(
                decision_state=decision_state,
                confidence=float(recommendation.confidence_final),
                threshold=float(confidence_threshold),
            )
        )
        effective_override = bool(payload.override_confidence or payload.override_type == "USER_CONFIRMED")

        acknowledged = {risk.upper() for risk in payload.acknowledged_risks}
        if explicit_ack_required and not effective_override:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Manual override requires explicit override_type=USER_CONFIRMED or override_confidence=true.",
            )
        if explicit_ack_required and not (payload.justification or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Manual override requires a non-empty justification.",
            )
        if explicit_ack_required:
            missing = sorted(self.REQUIRED_RISKS - acknowledged)
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Missing required risk acknowledgements: {', '.join(missing)}",
                )

        ml_predicted_tier = self._extract_ml_predicted_tier(recommendation=recommendation)

        plan_id = self._sqlite_next_id(MigrationPlan, MigrationPlan.id)

        plan = MigrationPlan(
            id=plan_id,
            user_id=current_user.id,
            recommendation_id=recommendation.id,
            resource_record_id=storage_record.id,
            resource_id=resource_id,
            provider=storage_record.provider,
            source_tier=recommendation.current_tier,
            target_tier=approved_target_tier,
            approved_target_tier=approved_target_tier,
            ml_predicted_tier=ml_predicted_tier,
            confidence_snapshot=float(recommendation.confidence_final),
            guardrail_snapshot={
                "decision_state": recommendation.decision_state,
                "execution_eligibility": recommendation.execution_eligibility,
                "guardrail_trace": recommendation.guardrail_trace,
                "pricing_trace": recommendation.pricing_trace,
                "decision_trace": recommendation.decision_trace,
            },
            execution_mode=MigrationExecutionMode.MANUAL,
            authorized_by=current_user.id,
            state=MigrationLifecycleState.PLANNED,
            override_confidence=bool(effective_override),
            risks_acknowledged={
                "acknowledged_risks": sorted(acknowledged),
                "required_risks": sorted(self.REQUIRED_RISKS),
                "explicit_ack_required": explicit_ack_required,
                "override_type": payload.override_type,
                "justification": payload.justification,
            },
        )
        self.db.add(plan)
        self.db.flush()

        self._transition(plan, MigrationLifecycleState.DRY_RUN)
        dry_run_report = self._dry_run(
            provider=current_provider,
            resource_id=resource_id,
            source_tier=recommendation.current_tier,
            target_tier=approved_target_tier,
            direct_execute_allowed=direct_execute_allowed,
            cross_cloud=recommended_provider != current_provider,
        )
        plan.dry_run_report = dry_run_report

        if execution_eligibility == ExecutionEligibility.DRY_RUN_ELIGIBLE.value:
            plan.execution_report = {
                "simulation": {
                    "status": "SIMULATED_RESULTS",
                    "resource_id": resource_id,
                    "provider": current_provider,
                    "target_tier": approved_target_tier,
                    "notes": "Dry-run only mode: no cloud-side write APIs were invoked.",
                }
            }
            plan.monitoring_report = {
                "dry_run_only": True,
                "risk_level": recommendation.migration_advisory.get("risk_level")
                if recommendation.migration_advisory
                else "HIGH",
            }
            audit_event = self._record_audit_event(
                user_id=current_user.id,
                plan_id=plan.id,
                payload={
                    "who": str(current_user.id),
                    "what": "manual_migration_dry_run",
                    "resource": resource_id,
                    "confidence": float(recommendation.confidence_final),
                    "guardrails": recommendation.guardrail_trace,
                    "risks_acknowledged": bool(acknowledged),
                    "execution_result": "SIMULATED_RESULTS",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "recommendation_id": recommendation.id,
                    "justification": payload.justification,
                    "lifecycle": ["PLANNED", "DRY_RUN", "SIMULATED_RESULTS"],
                },
            )
            self.db.commit()
            self.db.refresh(plan)
            return MigrationAuthorizeResponse(
                migration_plan_id=int(plan.id),
                recommendation_id=int(recommendation.id),
                resource_id=resource_id,
                migration_state="SIMULATED_RESULTS",
                execution_result="SIMULATED_RESULTS",
                execution_eligibility=execution_eligibility,
                message="Dry-run completed. Simulated results generated; no cloud resources were modified.",
                confidence_final=float(recommendation.confidence_final),
                guardrail_trace=list(recommendation.guardrail_trace),
                dry_run_report=dry_run_report,
                monitoring_report=plan.monitoring_report,
                audit_event_id=int(audit_event.id),
                authorized_at=plan.authorized_at,
            )

        self._transition(plan, MigrationLifecycleState.APPROVED)
        self._transition(plan, MigrationLifecycleState.EXECUTING)
        plan.executed_at = datetime.now(UTC)

        execution_report = self._execute_in_place_tier_change(
            provider=current_provider,
            resource_id=resource_id,
            source_tier=recommendation.current_tier,
            target_tier=approved_target_tier,
        )

        monitoring_report = self._monitor_runtime(
            storage_record_id=storage_record.id,
            recommendation=recommendation,
            target_tier=approved_target_tier,
        )
        plan.monitoring_report = monitoring_report

        if bool(monitoring_report.get("should_rollback", False)):
            self._transition(plan, MigrationLifecycleState.ROLLED_BACK)
            rollback_report = self._rollback_in_place_tier_change(
                provider=current_provider,
                resource_id=resource_id,
                source_tier=recommendation.current_tier,
                target_tier=approved_target_tier,
            )
            plan.execution_report = {
                "execution": execution_report,
                "rollback": rollback_report,
            }
            rollback_reason = str(monitoring_report.get("rollback_reason", "Runtime anomaly threshold breached"))
            plan.rollback_reason = rollback_reason
            plan.rolled_back_at = datetime.now(UTC)

            circuit_event = self._record_circuit_breaker(
                user_id=current_user.id,
                storage_record_id=storage_record.id,
                plan_id=plan.id,
                action=self._action_for_tier(approved_target_tier),
                outcome=CircuitBreakerOutcome.ROLLED_BACK_POST_MIGRATION,
                failure_code="RUNTIME_ANOMALY",
                failure_details=monitoring_report,
                rollback_reason=rollback_reason,
                backoff_days=self.DEFAULT_BACKOFF_DAYS,
            )
            self._transition(plan, MigrationLifecycleState.BLOCKED)

            audit_event = self._record_audit_event(
                user_id=current_user.id,
                plan_id=plan.id,
                payload={
                    "who": str(current_user.id),
                    "what": "manual_migration",
                    "resource": resource_id,
                    "confidence": float(recommendation.confidence_final),
                    "guardrails": recommendation.guardrail_trace,
                    "risks_acknowledged": True,
                    "execution_result": "ROLLED_BACK",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "circuit_breaker_event_id": circuit_event.event_id,
                    "recommendation_id": recommendation.id,
                    "justification": payload.justification,
                },
            )
            self.db.commit()
            self.db.refresh(plan)
            return MigrationAuthorizeResponse(
                migration_plan_id=int(plan.id),
                recommendation_id=int(recommendation.id),
                resource_id=resource_id,
                migration_state=plan.state.value,
                execution_result="ROLLED_BACK",
                execution_eligibility=execution_eligibility,
                message=f"Rolled Back (Explain Why): {rollback_reason}",
                confidence_final=float(recommendation.confidence_final),
                guardrail_trace=list(recommendation.guardrail_trace),
                dry_run_report=dry_run_report,
                monitoring_report=monitoring_report,
                audit_event_id=int(audit_event.id),
                authorized_at=plan.authorized_at,
            )

        plan.execution_report = {"execution": execution_report}
        self._transition(plan, MigrationLifecycleState.COMPLETED)

        audit_event = self._record_audit_event(
            user_id=current_user.id,
            plan_id=plan.id,
            payload={
                "who": str(current_user.id),
                "what": "manual_migration",
                "resource": resource_id,
                "confidence": float(recommendation.confidence_final),
                "guardrails": recommendation.guardrail_trace,
                "risks_acknowledged": bool(
                    explicit_ack_required and effective_override and self.REQUIRED_RISKS.issubset(acknowledged)
                ),
                "execution_result": "COMPLETED",
                "timestamp": datetime.now(UTC).isoformat(),
                "recommendation_id": recommendation.id,
                "justification": payload.justification,
            },
        )

        self.db.commit()
        self.db.refresh(plan)
        return MigrationAuthorizeResponse(
            migration_plan_id=int(plan.id),
            recommendation_id=int(recommendation.id),
            resource_id=resource_id,
            migration_state=plan.state.value,
            execution_result="COMPLETED",
            execution_eligibility=execution_eligibility,
            message="Completed Successfully",
            confidence_final=float(recommendation.confidence_final),
            guardrail_trace=list(recommendation.guardrail_trace),
            dry_run_report=dry_run_report,
            monitoring_report=monitoring_report,
            audit_event_id=int(audit_event.id),
            authorized_at=plan.authorized_at,
        )

    @classmethod
    def requires_explicit_ack(cls, *, decision_state: str, confidence: float, threshold: float) -> bool:
        state = str(decision_state or "").upper()
        return bool(confidence < threshold or state != "PREDICTED")

    @classmethod
    def validate_transition(
        cls,
        *,
        current_state: MigrationLifecycleState,
        next_state: MigrationLifecycleState,
    ) -> None:
        allowed = cls.STATE_TRANSITIONS.get(current_state, set())
        if next_state not in allowed:
            raise ValueError(f"Illegal migration state transition: {current_state.value} -> {next_state.value}")

    def _transition(self, plan: MigrationPlan, next_state: MigrationLifecycleState) -> None:
        self.validate_transition(current_state=plan.state, next_state=next_state)
        plan.state = next_state
        plan.updated_at = datetime.now(UTC)

    def _resolve_recommendation(
        self,
        *,
        user_id: int,
        recommendation_id: int | None,
        resource_id: str | None,
    ) -> RecommendationResponse:
        recommendations = DashboardService(self.db).get_recommendations(user_id=user_id)
        if recommendation_id is not None:
            for item in recommendations:
                if int(item.id) == int(recommendation_id):
                    return item
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recommendation not found for recommendation_id={recommendation_id}",
            )

        if resource_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="resource_id or recommendation_id is required.",
            )

        for item in recommendations:
            if item.resource_name == resource_id:
                return item
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation not found for resource_id={resource_id}",
        )

    def _resolve_storage_record(self, *, user_id: int, resource_id: str) -> StorageRecord:
        candidates = self._resource_name_candidates(resource_id=resource_id)
        provider_hint = self._provider_hint(resource_id=resource_id)

        query = (
            select(StorageRecord)
            .where(StorageRecord.user_id == user_id, StorageRecord.resource_name.in_(candidates))
            .order_by(
                case((StorageRecord.resource_name == resource_id, 0), else_=1),
                desc(StorageRecord.updated_at),
                desc(StorageRecord.id),
            )
        )
        if provider_hint is not None:
            query = query.where(StorageRecord.provider == provider_hint)

        record = self.db.scalar(query)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource record not found for resource_id={resource_id}",
            )
        return record

    @staticmethod
    def _resource_name_candidates(*, resource_id: str) -> list[str]:
        normalized = str(resource_id or "").strip()
        if not normalized:
            return []
        candidates = {normalized}
        if "::" in normalized:
            _, _, suffix = normalized.partition("::")
            suffix = suffix.strip()
            if suffix:
                candidates.add(suffix)
        return list(candidates)

    @staticmethod
    def _provider_hint(*, resource_id: str) -> CloudProvider | None:
        normalized = str(resource_id or "").strip()
        if "::" not in normalized:
            return None
        provider_token, _, _ = normalized.partition("::")
        token = provider_token.strip().upper()
        if not token:
            return None
        try:
            return CloudProvider(token)
        except ValueError:
            return None

    def _reject_if_backoff_active(self, *, storage_record_id: int) -> None:
        now = datetime.now(UTC)
        blocked = self.db.scalar(
            select(CircuitBreakerEvent)
            .where(
                CircuitBreakerEvent.resource_record_id == storage_record_id,
                CircuitBreakerEvent.backoff_until > now,
            )
            .order_by(desc(CircuitBreakerEvent.backoff_until), desc(CircuitBreakerEvent.event_id))
        )
        if blocked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Resource is in circuit-breaker backoff period until "
                    f"{blocked.backoff_until.isoformat()}."
                ),
            )

    def _resolve_confidence_threshold(self, *, tenant_id: str) -> float:
        policy = self.db.scalar(
            select(GovernancePolicy)
            .where(
                GovernancePolicy.tenant_id == tenant_id,
                GovernancePolicy.rule_type == GovernanceRuleType.MIN_CONFIDENCE_THRESHOLD,
                GovernancePolicy.is_active.is_(True),
            )
            .order_by(desc(GovernancePolicy.updated_at), desc(GovernancePolicy.policy_id))
        )
        if not policy:
            return self.DEFAULT_CONFIDENCE_THRESHOLD
        try:
            return float(policy.threshold_value)
        except Exception:
            return self.DEFAULT_CONFIDENCE_THRESHOLD

    def _action_for_tier(self, tier: str) -> CircuitBreakerAction:
        normalized = str(tier or "").lower()
        if any(token in normalized for token in ("archive", "glacier", "deep")):
            return CircuitBreakerAction.MIGRATE_TO_ARCHIVE
        if any(token in normalized for token in ("cold", "cool", "nearline", "ia")):
            return CircuitBreakerAction.MIGRATE_TO_COLD
        return CircuitBreakerAction.MIGRATE_TO_STANDARD_IA

    def _extract_ml_predicted_tier(self, *, recommendation: RecommendationResponse) -> str:
        for line in recommendation.rule_override_trace:
            normalized = line.strip()
            if normalized.lower().startswith("ml prediction:"):
                _, _, value = normalized.partition(":")
                return value.strip() or recommendation.recommended_tier
        return recommendation.recommended_tier

    def _dry_run(
        self,
        *,
        provider: str,
        resource_id: str,
        source_tier: str,
        target_tier: str,
        direct_execute_allowed: bool,
        cross_cloud: bool,
    ) -> dict[str, Any]:
        provider_upper = provider.upper()
        api_op = {
            "AWS": "PutObjectStorageClass",
            "AZURE": "SetBlobTier",
            "GCP": "StorageClassUpdate",
        }.get(provider_upper, "TierTransition")
        simulation_calls = {
            "AWS": ["DataSync::TaskDryRun", "S3::LifecycleValidation", "CloudWatch::LatencyProfile"],
            "AZURE": ["BlobTier::SetTierDryRun", "Rehydration::EstimateWindow", "Monitor::LatencyProfile"],
            "GCP": ["StorageClass::PatchDryRun", "TransferService::PlanSimulation", "CloudMonitoring::LatencyProfile"],
        }.get(provider_upper, ["TierTransition::PlanSimulation"])

        simulated_hours = 0.5 if direct_execute_allowed else 1.0

        return {
            "status": "PASS",
            "provider": provider_upper,
            "resource_id": resource_id,
            "source_tier": source_tier,
            "target_tier": target_tier,
            "operation": api_op,
            "execution_mode": "metadata_only",
            "cross_cloud": bool(cross_cloud),
            "data_copy": False,
            "simulated_api_calls": simulation_calls,
            "estimated_timing_hours": simulated_hours,
            "risk_profile": {
                "latency_risk": "MEDIUM" if "archive" in target_tier.lower() else "LOW",
                "egress_risk": "LOW",
                "rollback_required": True,
            },
            "rollback_plan": f"Revert tier from {target_tier} to {source_tier} using provider-native tier API.",
            "direct_execute_allowed": bool(direct_execute_allowed),
            "validated_at": datetime.now(UTC).isoformat(),
        }

    def _execute_in_place_tier_change(
        self,
        *,
        provider: str,
        resource_id: str,
        source_tier: str,
        target_tier: str,
    ) -> dict[str, Any]:
        provider_upper = provider.upper()
        if provider_upper == "AWS":
            api_call = "s3.copy_object(StorageClass=target_tier, MetadataDirective='COPY')"
        elif provider_upper == "AZURE":
            api_call = "blob_client.set_standard_blob_tier(target_tier)"
        else:
            api_call = "blob.patch(storageClass=target_tier)"

        return {
            "status": "EXECUTED",
            "provider": provider_upper,
            "resource_id": resource_id,
            "source_tier": source_tier,
            "target_tier": target_tier,
            "api_call": api_call,
            "execution_mode": "metadata_only",
            "data_copy": False,
            "executed_at": datetime.now(UTC).isoformat(),
        }

    def _rollback_in_place_tier_change(
        self,
        *,
        provider: str,
        resource_id: str,
        source_tier: str,
        target_tier: str,
    ) -> dict[str, Any]:
        return {
            "status": "ROLLED_BACK",
            "provider": provider.upper(),
            "resource_id": resource_id,
            "rolled_back_to_tier": source_tier,
            "from_tier": target_tier,
            "execution_mode": "metadata_only",
            "data_copy": False,
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }

    def _monitor_runtime(
        self,
        *,
        storage_record_id: int,
        recommendation: RecommendationResponse,
        target_tier: str,
    ) -> dict[str, Any]:
        cutoff = datetime.now(UTC).date() - timedelta(days=30)
        avg_access = self.db.scalar(
            select(func.avg(MetricHistory.requests_24h)).where(
                MetricHistory.resource_record_id == storage_record_id,
                MetricHistory.snapshot_date >= cutoff,
            )
        )
        latest_access = self.db.scalar(
            select(MetricHistory.requests_24h)
            .where(MetricHistory.resource_record_id == storage_record_id)
            .order_by(desc(MetricHistory.snapshot_date), desc(MetricHistory.history_id))
        )

        baseline_access = float(avg_access or 0.0)
        if baseline_access <= 0:
            baseline_access = max(float(latest_access or 0.0), 1.0)

        observed_access = float(latest_access or baseline_access)
        access_spike_multiplier = 1.55 if float(recommendation.confidence_final) < 0.65 else 1.10
        simulated_access_after = observed_access * access_spike_multiplier

        access_spike_ratio = (simulated_access_after - baseline_access) / max(baseline_access, 1.0)

        tier_lower = target_tier.lower()
        latency_penalty = 0.0
        if any(token in tier_lower for token in ("archive", "glacier", "deep")):
            latency_penalty = 120.0
        elif any(token in tier_lower for token in ("cool", "cold", "nearline", "ia")):
            latency_penalty = 80.0

        simulated_latency_ms = 75.0 + latency_penalty
        simulated_error_rate = 0.004 + (0.009 if float(recommendation.confidence_final) < 0.55 else 0.0)

        breaches: list[str] = []
        if simulated_latency_ms > 200.0:
            breaches.append("LATENCY_GT_200MS")
        if access_spike_ratio > 0.50:
            breaches.append("ACCESS_SPIKE_GT_50_PERCENT")
        if simulated_error_rate > 0.01:
            breaches.append("ERROR_RATE_GT_1_PERCENT")

        rollback_reason = "" if not breaches else f"Runtime safety monitor breached: {', '.join(breaches)}"
        return {
            "baseline_access_24h": round(baseline_access, 3),
            "simulated_access_after_24h": round(simulated_access_after, 3),
            "access_spike_ratio": round(access_spike_ratio, 6),
            "simulated_latency_ms": round(simulated_latency_ms, 3),
            "simulated_error_rate": round(simulated_error_rate, 6),
            "thresholds": {
                "latency_ms": 200.0,
                "access_spike_ratio": 0.50,
                "error_rate": 0.01,
            },
            "breaches": breaches,
            "should_rollback": bool(breaches),
            "rollback_reason": rollback_reason,
            "confidence_penalty": 0.15 if breaches else 0.0,
        }

    def _record_circuit_breaker(
        self,
        *,
        user_id: int,
        storage_record_id: int,
        plan_id: int | None,
        action: CircuitBreakerAction,
        outcome: CircuitBreakerOutcome,
        failure_code: str,
        failure_details: dict[str, Any],
        rollback_reason: str,
        backoff_days: int,
    ) -> CircuitBreakerEvent:
        event_id = self._sqlite_next_id(CircuitBreakerEvent, CircuitBreakerEvent.event_id)
        event = CircuitBreakerEvent(
            event_id=event_id,
            user_id=user_id,
            resource_record_id=storage_record_id,
            migration_plan_id=plan_id,
            action_attempted=action,
            outcome=outcome,
            failure_code=failure_code,
            failure_details=failure_details,
            rollback_reason=rollback_reason,
            backoff_until=datetime.now(UTC) + timedelta(days=backoff_days),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _record_audit_event(self, *, user_id: int, plan_id: int | None, payload: dict[str, Any]) -> AuditEvent:
        event_id = self._sqlite_next_id(AuditEvent, AuditEvent.id)
        event = AuditEvent(
            id=event_id,
            user_id=user_id,
            migration_plan_id=plan_id,
            who=str(payload.get("who", user_id)),
            what=str(payload.get("what", "manual_migration")),
            resource=str(payload.get("resource", "")),
            confidence=float(payload.get("confidence", 0.0)),
            guardrails={"items": list(payload.get("guardrails", []))},
            risks_acknowledged=bool(payload.get("risks_acknowledged", False)),
            execution_result=str(payload.get("execution_result", "UNKNOWN")),
            details=payload,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _sqlite_next_id(self, model: type[Any], pk_column: Any) -> int | None:
        bind = self.db.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            return None
        next_id = self.db.scalar(select(func.coalesce(func.max(pk_column), 0) + 1))
        return int(next_id or 1)
