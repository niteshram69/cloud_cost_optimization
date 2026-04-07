from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import CloudProvider, FinOpsResource
from backend.app.schemas.ingest import ResourceIngestItem


class ResourceRepository:
    """Persistence-only repository for ingested resources."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, payload: ResourceIngestItem) -> FinOpsResource:
        size_mb = float(payload.object_size_bytes) / (1024.0 * 1024.0)
        days_observed = max(int(payload.object_age_days), 1)
        has_real_billing = payload.billing_realism != "ESTIMATE"
        storage_cost_per_gb = float(payload.storage_cost_per_gb) if payload.storage_cost_per_gb is not None else 0.0
        retrieval_cost_per_gb = (
            float(payload.retrieval_cost_per_gb) if payload.retrieval_cost_per_gb is not None else 0.0
        )
        model = FinOpsResource(
            resource_id=payload.resource_id,
            provider=CloudProvider(payload.provider),
            region=str(payload.region),
            intent_tier=str(payload.intent_tier) if payload.intent_tier else None,
            object_size_bytes=int(payload.object_size_bytes),
            object_age_days=int(payload.object_age_days),
            last_access_days=int(payload.last_access_days),
            requests_90d=int(payload.requests_90d),
            read_write_ratio=float(payload.read_write_ratio),
            access_std_dev=float(payload.access_std_dev),
            storage_cost_per_gb=storage_cost_per_gb,
            retrieval_cost_per_gb=retrieval_cost_per_gb,
            estimated_monthly_cost_usd=float(payload.estimated_monthly_cost_usd),
            size_mb=size_mb,
            requests_30d=int(payload.requests_30d),
            days_observed=days_observed,
            has_real_billing=has_real_billing,
            current_storage_tier=str(payload.current_storage_tier),
            billing_realism=str(payload.billing_realism),
            integration_permission=str(payload.integration_permission),
            raw_payload=payload.model_dump(),
        )
        self.db.add(model)
        await self.db.flush()
        await self.db.refresh(model)
        return model
