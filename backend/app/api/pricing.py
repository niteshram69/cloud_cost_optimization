from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_role
from backend.app.database import get_db
from backend.app.models import User, UserRole
from backend.app.schemas.pricing import (
    AzurePricingSyncResponse,
    CloudPricingSyncResponse,
    PricingCandidateResponse,
    PricingDecisionRequest,
    PricingDecisionResponse,
    PricingVersionResponse,
    TopSavingsResponse,
)
from backend.app.services.pricing_intelligence_service import (
    AWSPricingIngestionService,
    AzurePricingIngestionService,
    GCPPricingIngestionService,
    PricingDecisionInput,
    PricingDecisionService,
)

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


def _admin_user_guard(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


@router.post(
    "/admin/azure/sync",
    response_model=AzurePricingSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_azure_pricing(
    max_pages: int = Query(default=12, ge=1, le=100),
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> AzurePricingSyncResponse:
    service = AzurePricingIngestionService(db)
    try:
        result = await service.sync_latest(max_pages=max_pages)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Azure pricing sync failed: {exc}") from exc
    return AzurePricingSyncResponse(**result)


@router.post(
    "/admin/aws/sync",
    response_model=CloudPricingSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_aws_pricing(
    max_records: int = Query(default=1000, ge=10, le=20000),
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> CloudPricingSyncResponse:
    service = AWSPricingIngestionService(db)
    try:
        result = await service.sync_latest(max_records=max_records)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AWS pricing sync failed: {exc}") from exc
    return CloudPricingSyncResponse(**result)


@router.post(
    "/admin/gcp/sync",
    response_model=CloudPricingSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_gcp_pricing(
    max_pages: int = Query(default=8, ge=1, le=100),
    max_records: int = Query(default=1000, ge=10, le=20000),
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> CloudPricingSyncResponse:
    service = GCPPricingIngestionService(db)
    try:
        result = await service.sync_latest(max_pages=max_pages, max_records=max_records)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GCP pricing sync failed: {exc}") from exc
    return CloudPricingSyncResponse(**result)


@router.get("/version/latest", response_model=PricingVersionResponse)
def latest_pricing_version(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PricingVersionResponse:
    _ = current_user
    service = PricingDecisionService(db)
    result = service.get_latest_version_metadata()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pricing data available. Sync Azure pricing first.",
        )
    return PricingVersionResponse(**result)


@router.post("/decision", response_model=PricingDecisionResponse)
def pricing_decision(
    payload: PricingDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PricingDecisionResponse:
    _ = current_user
    service = PricingDecisionService(db)
    try:
        result = service.decide(
            PricingDecisionInput(
                resource_id=payload.resource_id,
                data_temperature=payload.data_temperature,
                storage_gb=payload.storage_gb,
                monthly_retrieval_gb=payload.monthly_retrieval_gb,
                region_preference=payload.region_preference,
                current_cloud=payload.current_cloud,
                current_tier=payload.current_tier,
                current_monthly_cost=payload.current_monthly_cost,
                currency=payload.currency,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PricingDecisionResponse(
        resource_id=result.resource_id,
        data_temperature=result.data_temperature,
        current_cloud=result.current_cloud,
        current_tier=result.current_tier,
        recommended_cloud=result.recommended_cloud,
        recommended_tier=result.recommended_tier,
        current_monthly_cost=result.current_monthly_cost,
        optimized_monthly_cost=result.optimized_monthly_cost,
        estimated_savings_percent=result.estimated_savings_percent,
        pricing_version=result.pricing_version,
        currency=result.currency,
        region_preference=result.region_preference,
        candidates=[
            PricingCandidateResponse(
                cloud=item.cloud,
                native_tier=item.native_tier,
                canonical_tier=item.canonical_tier,
                region=item.region,
                storage_price_per_gb=item.storage_price_per_gb,
                retrieval_price_per_gb=item.retrieval_price_per_gb,
                monthly_cost=item.monthly_cost,
                currency=item.currency,
            )
            for item in result.candidates
        ],
        cost_assumptions=result.cost_assumptions,
        explanation=result.explanation,
    )


@router.get("/opportunities/top", response_model=TopSavingsResponse)
def top_savings_opportunities(
    limit: int = Query(default=10, ge=1, le=100),
    currency: str = Query(default="USD", min_length=3, max_length=8),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopSavingsResponse:
    service = PricingDecisionService(db)
    result = service.top_savings_opportunities(
        user_id=current_user.id,
        limit=limit,
        currency=currency,
    )
    return TopSavingsResponse(**result)
