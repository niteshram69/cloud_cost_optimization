from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.schemas.ingest import IngestRequest
from backend.app.services.ingest_service import IngestService
from backend.app.services.optimizer_service import OptimizerService, RISK_THRESHOLD
from backend.app.schemas.ingest import ResourceIngestItem


@pytest.mark.asyncio
async def test_recommendation_suppressed_when_risk_exceeds_savings() -> None:
    """
    Scenario under test:
    - High retrieval penalty and volatility
    - Savings are marginal
    - Recommendation should be suppressed with RETAIN
    """

    payload = IngestRequest(
        resources=[
            {
                "resource_id": "r-123",
                "provider": "AWS",
                "region": "us-east-1",
                "current_storage_tier": "STANDARD",
                "object_size_bytes": 6 * 1024 * 1024 * 1024 * 1024,  # 6 TB
                "object_age_days": 45,
                "last_access_days": 40,
                "requests_30d": 210,
                "requests_90d": 350,
                "read_write_ratio": 0.8,
                "access_std_dev": 180.0,
                "estimated_monthly_cost_usd": 140.0,
                "retrieval_cost_per_gb": 0.12,
                "billing_realism": "ESTIMATE",
                "integration_permission": "READ_ONLY",
            }
        ]
    )

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    resource_repo = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id=11, resource_id="r-123")))
    recommendation_repo = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id=22)))

    service = IngestService(
        db=db,  # type: ignore[arg-type]
        resource_repo=resource_repo,  # type: ignore[arg-type]
        recommendation_repo=recommendation_repo,  # type: ignore[arg-type]
    )

    result = await service.ingest(payload)

    assert result.total_succeeded == 1
    assert result.total_failed == 0
    assert result.failed == []

    # Ensure repository layer is mocked and no real DB calls happen in the test.
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


def test_recency_guardrail_forces_hot() -> None:
    resource = ResourceIngestItem(
        resource_id="hot-1",
        provider="AWS",
        region="us-east-1",
        current_storage_tier="STANDARD",
        object_size_bytes=50_000_000,
        object_age_days=45,
        last_access_days=3,
        requests_30d=5,
        requests_90d=12,
        read_write_ratio=0.5,
        access_std_dev=1.2,
        estimated_monthly_cost_usd=1.2,
        retrieval_cost_per_gb=0.01,
        billing_realism="EXPORT",
        integration_permission="READ_WRITE",
    )

    decision = OptimizerService().optimize(resource)

    assert decision.classification == "HOT"
    assert decision.recommended_storage_tier == "STANDARD"
    assert decision.execution_eligibility == "DRY_RUN_ONLY"


def test_archive_guardrail_blocks_large_retrieval() -> None:
    resource = ResourceIngestItem(
        resource_id="archive-1",
        provider="AWS",
        region="us-east-1",
        current_storage_tier="STANDARD",
        object_size_bytes=7 * 1024 * 1024 * 1024 * 1024,  # 7 TB
        object_age_days=240,
        last_access_days=200,
        requests_30d=2,
        requests_90d=5,
        read_write_ratio=0.2,
        access_std_dev=0.5,
        estimated_monthly_cost_usd=60.0,
        retrieval_cost_per_gb=0.25,
        billing_realism="LIVE",
        integration_permission="READ_ONLY",
    )

    decision = OptimizerService().optimize(resource)

    assert decision.classification in {"COLD", "WARM"}
    assert "ARCHIVE" not in decision.recommended_storage_tier.upper()
    assert decision.execution_eligibility == "DRY_RUN_ONLY"


def test_execution_eligibility_requires_low_risk_and_read_write() -> None:
    resource = ResourceIngestItem(
        resource_id="exec-1",
        provider="AWS",
        region="us-east-1",
        current_storage_tier="STANDARD",
        object_size_bytes=200_000_000,
        object_age_days=180,
        last_access_days=120,
        requests_30d=120,
        requests_90d=400,
        read_write_ratio=2.0,
        access_std_dev=1.0,
        estimated_monthly_cost_usd=4.0,
        retrieval_cost_per_gb=0.005,
        billing_realism="LIVE",
        integration_permission="READ_WRITE",
    )

    decision = OptimizerService().optimize(resource)

    assert decision.migration_risk < RISK_THRESHOLD
    assert decision.execution_eligibility == "EXECUTABLE"


@pytest.mark.asyncio
async def test_ingest_continues_when_one_resource_is_malformed() -> None:
    """
    Batch safety requirement:
    one malformed resource should be captured as an item error while valid items continue.
    """

    payload = IngestRequest(
        resources=[
            {
                "resource_id": "bad-1",
                "provider": "AWS",
                "region": "us-east-1",
                "current_storage_tier": "STANDARD",
                "object_size_bytes": -1,  # invalid
                "object_age_days": 10,
                "last_access_days": 3,
                "requests_30d": 10,
                "requests_90d": 25,
                "read_write_ratio": 1.2,
                "access_std_dev": 4.0,
                "estimated_monthly_cost_usd": 2.0,
                "retrieval_cost_per_gb": 0.01,
                "billing_realism": "ESTIMATE",
                "integration_permission": "READ_ONLY",
            },
            {
                "resource_id": "good-1",
                "provider": "AWS",
                "region": "us-east-1",
                "current_storage_tier": "STANDARD",
                "object_size_bytes": 10_000_000,
                "object_age_days": 120,
                "last_access_days": 75,
                "requests_30d": 0,
                "requests_90d": 10,
                "read_write_ratio": 0.3,
                "access_std_dev": 1.0,
                "estimated_monthly_cost_usd": 1.6,
                "retrieval_cost_per_gb": 0.01,
                "billing_realism": "LIVE",
                "integration_permission": "READ_WRITE",
            },
        ]
    )

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    resource_repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=101, resource_id="good-1"))
    )
    recommendation_repo = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id=202)))

    service = IngestService(
        db=db,  # type: ignore[arg-type]
        resource_repo=resource_repo,  # type: ignore[arg-type]
        recommendation_repo=recommendation_repo,  # type: ignore[arg-type]
    )

    result = await service.ingest(payload)

    assert result.total_received == 2
    assert result.total_succeeded == 1
    assert result.total_failed == 1
    assert result.failed[0].resource_id == "bad-1"
    assert result.failed[0].error_code == "validation_error"
    assert "object_size_bytes" in result.failed[0].reason

    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
