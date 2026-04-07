"""Business logic for decision generation and webhook management."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import DecisionAction
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security import generate_webhook_secret
from app.modules.classification.models import ClassificationResult
from app.modules.cost.models import CostRecord
from app.modules.decisions.engine import RuleEngine
from app.modules.decisions.models import Decision
from app.modules.decisions.repository import DecisionRepository, WebhookLogRepository
from app.modules.decisions.schemas import (
    DecisionApproveRequest,
    DecisionCreateRequest,
    DecisionDismissRequest,
    DecisionStatsResponse,
)
from app.modules.decisions.webhooks import WebhookDeliverer


class DecisionService:
    """Service for managing decisions and recommendations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DecisionRepository(db)
        self.log_repo = WebhookLogRepository(db)
        self.engine = RuleEngine()
        self.webhook_deliverer = WebhookDeliverer()
    
    async def generate_decisions_from_cost(
        self,
        user_id: int,
        cost_record: CostRecord,
        classification: ClassificationResult | None = None,
    ) -> list[Decision]:
        """Generate decisions from a cost record using rule engine."""
        # Evaluate rules
        matches = self.engine.evaluate_record(cost_record, classification)
        
        decisions = []
        for match in matches:
            # Check if decision already exists for this cost + rule
            # (Skip duplicates)
            
            decision = Decision(
                cost_record_id=cost_record.id,
                user_id=user_id,
                recommendation=match['recommendation'],
                action_type=match['action'],
                confidence=match['confidence'],
                estimated_savings_monthly=match['estimated_savings_monthly'],
                estimated_cost_to_implement=match['estimated_cost_to_implement'],
                is_automated=match['auto_execute'],
                rule_id=match['rule_id'],
                rule_explanation=f"Matched rule: {match['rule_name']}",
                context=match['context'],
            )
            
            created = await self.repo.create(decision)
            decisions.append(created)
        
        return decisions
    
    async def create_manual_decision(
        self,
        user_id: int,
        data: DecisionCreateRequest,
    ) -> Decision:
        """Create a manual decision."""
        decision = Decision(
            cost_record_id=data.cost_record_id,
            user_id=user_id,
            recommendation=data.recommendation,
            action_type=data.action_type,
            confidence=data.confidence,
            estimated_savings_monthly=data.estimated_savings_monthly,
            estimated_cost_to_implement=data.estimated_cost_to_implement,
            is_automated=data.is_automated,
            webhook_url=str(data.webhook_url) if data.webhook_url else None,
        )
        
        # Generate webhook secret if webhook URL provided
        if decision.webhook_url:
            decision.webhook_secret = generate_webhook_secret()
        
        return await self.repo.create(decision)
    
    async def approve_decision(
        self,
        user_id: int,
        decision_id: int,
        data: DecisionApproveRequest,
        approved_by: str,
    ) -> Decision:
        """Approve a decision and trigger execution."""
        decision = await self.repo.get_by_id(decision_id, user_id)
        if not decision:
            raise ResourceNotFoundError("Decision", str(decision_id))
        
        if decision.dismissed_at:
            raise ValidationError("Cannot approve a dismissed decision")
        
        # Update approval
        decision.approved_at = datetime.now(timezone.utc)
        decision.approved_by = approved_by
        
        # Set webhook URL if provided
        if data.webhook_url:
            decision.webhook_url = str(data.webhook_url)
            if not decision.webhook_secret:
                decision.webhook_secret = generate_webhook_secret()
        
        await self.repo.update(decision)
        
        # Trigger webhook delivery
        if decision.webhook_url:
            await self.deliver_webhook(user_id, decision_id)
        
        return decision
    
    async def dismiss_decision(
        self,
        user_id: int,
        decision_id: int,
        data: DecisionDismissRequest,
        dismissed_by: str,
    ) -> Decision:
        """Dismiss a decision."""
        decision = await self.repo.get_by_id(decision_id, user_id)
        if not decision:
            raise ResourceNotFoundError("Decision", str(decision_id))
        
        if decision.executed_at:
            raise ValidationError("Cannot dismiss an executed decision")
        
        decision.dismissed_at = datetime.now(timezone.utc)
        decision.dismissed_by = dismissed_by
        decision.dismiss_reason = data.reason
        
        await self.repo.update(decision)
        return decision
    
    async def deliver_webhook(
        self,
        user_id: int,
        decision_id: int,
    ) -> list[dict]:
        """Deliver webhook for a decision."""
        decision = await self.repo.get_by_id(decision_id, user_id)
        if not decision:
            raise ResourceNotFoundError("Decision", str(decision_id))
        
        if not decision.webhook_url:
            raise ValidationError("No webhook URL configured for this decision")
        
        # Deliver webhook
        logs = await self.webhook_deliverer.deliver_with_retry(decision)
        
        # Save logs
        for log in logs:
            await self.log_repo.create(log)
        
        # Update decision with final status
        await self.repo.update(decision)
        
        return [
            {
                'attempt': log.attempt_number,
                'status': log.status,
                'status_code': log.status_code,
                'error': log.error_message,
                'duration_ms': log.duration_ms,
            }
            for log in logs
        ]
    
    async def get_decision(
        self,
        user_id: int,
        decision_id: int,
    ) -> Decision:
        """Get a specific decision."""
        decision = await self.repo.get_by_id(decision_id, user_id)
        if not decision:
            raise ResourceNotFoundError("Decision", str(decision_id))
        return decision
    
    async def list_decisions(
        self,
        user_id: int,
        status: str | None = None,
        action_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Decision]:
        """List decisions for a user."""
        return await self.repo.list_by_user(user_id, status, action_type, limit, offset)
    
    async def get_statistics(self, user_id: int) -> DecisionStatsResponse:
        """Get decision statistics."""
        stats = await self.repo.get_statistics(user_id)
        
        # Count webhook deliveries
        from sqlalchemy import select, func
        from app.modules.decisions.models import WebhookLog
        
        result = await self.db.execute(
            select(func.count(WebhookLog.id))
            .join(Decision)
            .where(Decision.user_id == user_id)
        )
        webhook_count = result.scalar() or 0
        
        return DecisionStatsResponse(
            total_decisions=stats['total'],
            by_status=stats['by_status'],
            by_action_type=stats['by_action_type'],
            pending_approval=stats['pending_approval'],
            total_estimated_savings=stats['total_estimated_savings'],
            automated_executions=stats['automated_executions'],
            webhook_deliveries=webhook_count,
        )
    
    async def get_webhook_logs(
        self,
        user_id: int,
        decision_id: int,
    ) -> list[dict]:
        """Get webhook delivery logs for a decision."""
        # Verify ownership
        decision = await self.get_decision(user_id, decision_id)
        
        logs = await self.log_repo.get_by_decision(decision_id)
        
        return [
            {
                'id': log.id,
                'attempt_number': log.attempt_number,
                'status': log.status,
                'status_code': log.status_code,
                'error_message': log.error_message,
                'triggered_at': log.triggered_at,
                'duration_ms': log.duration_ms,
            }
            for log in logs
        ]
