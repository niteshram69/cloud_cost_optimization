from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories import RecommendationRepository, ResourceRepository
from backend.app.schemas.ingest import IngestItemError, IngestItemSuccess, IngestRequest, IngestResponse, ResourceIngestItem
from backend.app.services.optimizer_service import OptimizerService

logger = logging.getLogger(__name__)


class IngestService:
    """
    Application-layer orchestrator for batch ingestion.

    This service owns control-flow and resiliency. Business logic remains in OptimizerService.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        resource_repo: ResourceRepository | None = None,
        recommendation_repo: RecommendationRepository | None = None,
        optimizer: OptimizerService | None = None,
    ) -> None:
        self.db = db
        self.resource_repo = resource_repo or ResourceRepository(db)
        self.recommendation_repo = recommendation_repo or RecommendationRepository(db)
        self.optimizer = optimizer or OptimizerService()

    async def ingest(self, payload: IngestRequest) -> IngestResponse:
        started_at = datetime.now(UTC)
        success: list[IngestItemSuccess] = []
        failed: list[IngestItemError] = []

        for index, item in enumerate(payload.resources):
            resource_id = None
            if isinstance(item, dict):
                candidate_resource_id = item.get("resource_id")
                if isinstance(candidate_resource_id, str):
                    resource_id = candidate_resource_id

            try:
                resource = ResourceIngestItem.model_validate(item, strict=True)
            except ValidationError as exc:
                failed.append(
                    IngestItemError(
                        index=index,
                        resource_id=resource_id,
                        error_code="validation_error",
                        reason="; ".join(self._format_validation_errors(exc)),
                    )
                )
                continue

            try:
                decision = self.optimizer.optimize(resource)

                # Per-resource commit preserves partial success semantics.
                db_resource = await self.resource_repo.create(payload=resource)
                db_recommendation = await self.recommendation_repo.create(
                    resource_pk=db_resource.id,
                    resource_id=db_resource.resource_id,
                    decision=decision,
                )
                await self.db.commit()

                success.append(
                    IngestItemSuccess(
                        index=index,
                        resource_id=resource.resource_id,
                        resource_pk=db_resource.id,
                        recommendation_pk=db_recommendation.id,
                        decision=decision,
                    )
                )
            except Exception as exc:
                await self.db.rollback()
                logger.exception("Resource ingestion failed at index=%s resource_id=%s", index, resource.resource_id)
                failed.append(
                    IngestItemError(
                        index=index,
                        resource_id=resource_id,
                        error_code="ingestion_failed",
                        reason=str(exc),
                    )
                )

        completed_at = datetime.now(UTC)
        return IngestResponse(
            ingestion_started_at=started_at,
            ingestion_completed_at=completed_at,
            total_received=len(payload.resources),
            total_succeeded=len(success),
            total_failed=len(failed),
            succeeded=success,
            failed=failed,
        )

    @staticmethod
    def _format_validation_errors(exc: ValidationError) -> list[str]:
        errors: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            msg = str(err.get("msg", "Validation failed"))
            errors.append(f"{loc}: {msg}" if loc else msg)
        return errors or ["Validation failed"]
