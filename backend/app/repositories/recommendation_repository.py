from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import CloudProvider, DecisionState, FinOpsRecommendation, OptimizationAction
from backend.app.schemas.ingest import OptimizerDecisionSchema


class RecommendationRepository:
    """Persistence-only repository for optimization decisions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        resource_pk: int,
        resource_id: str,
        decision: OptimizerDecisionSchema,
    ) -> FinOpsRecommendation:
        recommendation_hash = self._recommendation_hash(decision)
        existing = await self.db.scalar(
            select(FinOpsRecommendation).where(
                FinOpsRecommendation.resource_id == resource_id,
                FinOpsRecommendation.recommendation_hash == recommendation_hash,
            )
        )
        if existing:
            return existing

        model = FinOpsRecommendation(
            resource_pk=resource_pk,
            resource_id=resource_id,
            recommendation_hash=recommendation_hash,
            action=OptimizationAction(decision.action),
            decision_state=DecisionState(decision.decision_state),
            classification=str(decision.classification),
            recommended_provider=CloudProvider(decision.recommended_provider),
            recommended_storage_tier=decision.recommended_storage_tier,
            confidence_final=float(decision.confidence_final),
            rule_trace="\\n".join(decision.rule_trace),
        )
        self.db.add(model)
        try:
            await self.db.flush()
            await self.db.refresh(model)
            return model
        except IntegrityError:
            await self.db.rollback()
            existing = await self.db.scalar(
                select(FinOpsRecommendation).where(
                    FinOpsRecommendation.resource_id == resource_id,
                    FinOpsRecommendation.recommendation_hash == recommendation_hash,
                )
            )
            if existing:
                return existing
            raise

    @staticmethod
    def _recommendation_hash(decision: OptimizerDecisionSchema) -> str:
        payload = {
            "action": str(decision.action),
            "decision_state": str(decision.decision_state),
            "classification": str(decision.classification),
            "recommended_provider": str(decision.recommended_provider),
            "recommended_storage_tier": str(decision.recommended_storage_tier),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
