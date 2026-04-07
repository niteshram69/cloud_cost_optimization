"""Decision and webhook API routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import CurrentUserDependency
from app.modules.decisions.schemas import (
    DecisionApproveRequest,
    DecisionCreateRequest,
    DecisionDismissRequest,
    DecisionResponse,
    DecisionStatsResponse,
    WebhookDeliveryRequest,
)
from app.modules.decisions.service import DecisionService

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("/stats", response_model=DecisionStatsResponse)
async def get_statistics(
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get decision statistics for current user."""
    service = DecisionService(db)
    stats = await service.get_statistics(int(current_user["id"]))
    return stats


@router.get("/", response_model=list[DecisionResponse])
async def list_decisions(
    status: str | None = None,
    action_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """List decisions for current user."""
    service = DecisionService(db)
    decisions = await service.list_decisions(
        int(current_user["id"]),
        status,
        action_type,
        limit,
        offset,
    )
    return decisions


@router.post("/", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def create_decision(
    data: DecisionCreateRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Create a manual decision/recommendation."""
    service = DecisionService(db)
    decision = await service.create_manual_decision(int(current_user["id"]), data)
    return decision


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific decision."""
    service = DecisionService(db)
    decision = await service.get_decision(int(current_user["id"]), decision_id)
    return decision


@router.post("/{decision_id}/approve", response_model=DecisionResponse)
async def approve_decision(
    decision_id: int,
    data: DecisionApproveRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Approve a decision and trigger execution."""
    service = DecisionService(db)
    decision = await service.approve_decision(
        int(current_user["id"]),
        decision_id,
        data,
        current_user["email"],
    )
    return decision


@router.post("/{decision_id}/dismiss", response_model=DecisionResponse)
async def dismiss_decision(
    decision_id: int,
    data: DecisionDismissRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a decision."""
    service = DecisionService(db)
    decision = await service.dismiss_decision(
        int(current_user["id"]),
        decision_id,
        data,
        current_user["email"],
    )
    return decision


@router.post("/{decision_id}/deliver-webhook")
async def deliver_webhook(
    decision_id: int,
    data: WebhookDeliveryRequest,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Trigger webhook delivery for a decision."""
    service = DecisionService(db)
    logs = await service.deliver_webhook(int(current_user["id"]), decision_id)
    return {
        'decision_id': decision_id,
        'delivery_attempts': logs,
        'status': 'completed' if any(l['status'] == 'success' for l in logs) else 'failed',
    }


@router.get("/{decision_id}/webhook-logs")
async def get_webhook_logs(
    decision_id: int,
    current_user: dict = CurrentUserDependency,
    db: AsyncSession = Depends(get_db),
):
    """Get webhook delivery logs for a decision."""
    service = DecisionService(db)
    logs = await service.get_webhook_logs(int(current_user["id"]), decision_id)
    return {
        'decision_id': decision_id,
        'logs': logs,
        'total_attempts': len(logs),
    }
