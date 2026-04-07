"""Database access layer for decision operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.decisions.models import Decision, WebhookLog


class DecisionRepository:
    """Repository for decision operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, decision_id: int, user_id: int) -> Decision | None:
        """Get decision by ID and user ID."""
        result = await self.db.execute(
            select(Decision).where(
                Decision.id == decision_id,
                Decision.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_by_user(
        self,
        user_id: int,
        status: str | None = None,
        action_type: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[Decision]:
        """List decisions for a user with optional filters."""
        query = select(Decision).where(Decision.user_id == user_id)
        
        if status:
            query = query.where(Decision.webhook_status == status)
        if action_type:
            query = query.where(Decision.action_type == action_type)
        
        result = await self.db.execute(
            query.order_by(Decision.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, decision: Decision) -> Decision:
        """Create a new decision."""
        self.db.add(decision)
        await self.db.flush()
        await self.db.refresh(decision)
        return decision
    
    async def update(self, decision: Decision) -> Decision:
        """Update a decision."""
        await self.db.flush()
        await self.db.refresh(decision)
        return decision
    
    async def get_statistics(self, user_id: int) -> dict:
        """Get decision statistics for a user."""
        # Count by status
        status_result = await self.db.execute(
            select(
                Decision.webhook_status,
                func.count(Decision.id).label('count')
            )
            .where(Decision.user_id == user_id)
            .group_by(Decision.webhook_status)
        )
        by_status = {row.webhook_status: row.count for row in status_result.all()}
        
        # Count by action type
        action_result = await self.db.execute(
            select(
                Decision.action_type,
                func.count(Decision.id).label('count')
            )
            .where(Decision.user_id == user_id)
            .group_by(Decision.action_type)
        )
        by_action = {row.action_type: row.count for row in action_result.all()}
        
        # Total estimated savings
        savings_result = await self.db.execute(
            select(func.sum(Decision.estimated_savings_monthly))
            .where(
                Decision.user_id == user_id,
                Decision.dismissed_at == None
            )
        )
        total_savings = savings_result.scalar() or 0
        
        # Pending approval count
        pending = await self.db.execute(
            select(func.count(Decision.id))
            .where(
                Decision.user_id == user_id,
                Decision.approved_at == None,
                Decision.dismissed_at == None,
            )
        )
        pending_count = pending.scalar() or 0
        
        # Automated executions
        automated = await self.db.execute(
            select(func.count(Decision.id))
            .where(
                Decision.user_id == user_id,
                Decision.is_automated == True,
                Decision.executed_at != None,
            )
        )
        automated_count = automated.scalar() or 0
        
        return {
            'total': sum(by_status.values()),
            'by_status': by_status,
            'by_action_type': by_action,
            'total_estimated_savings': total_savings,
            'pending_approval': pending_count,
            'automated_executions': automated_count,
        }


class WebhookLogRepository:
    """Repository for webhook log operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_decision(
        self,
        decision_id: int,
        limit: int = 50
    ) -> list[WebhookLog]:
        """Get webhook logs for a decision."""
        result = await self.db.execute(
            select(WebhookLog)
            .where(WebhookLog.decision_id == decision_id)
            .order_by(WebhookLog.triggered_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def create(self, log: WebhookLog) -> WebhookLog:
        """Create a webhook log entry."""
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log
