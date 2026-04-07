"""Celery tasks for background decision processing."""

from celery import shared_task

from app.core.database import AsyncSessionLocal
from app.modules.decisions.service import DecisionService


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_decisions_for_cost_record(
    self,
    user_id: int,
    cost_record_id: int,
) -> dict:
    """
    Generate decisions for a cost record using the rule engine.
    
    Args:
        user_id: ID of the user
        cost_record_id: ID of the cost record to analyze
    
    Returns:
        Dict with generated decisions
    """
    async def _generate():
        async with AsyncSessionLocal() as db:
            from app.modules.cost.repository import CostRepository
            from app.modules.classification.repository import ClassificationRepository
            
            # Get cost record
            cost_repo = CostRepository(db)
            cost_record = await cost_repo.get_by_id(cost_record_id, user_id)
            
            if not cost_record:
                return {'error': f'Cost record {cost_record_id} not found'}
            
            # Get classification if available
            classification_repo = ClassificationRepository(db)
            classification = None
            if cost_record.metadata_record_id:
                classification = await classification_repo.get_by_metadata(
                    cost_record.metadata_record_id,
                    user_id
                )
            
            # Generate decisions
            service = DecisionService(db)
            decisions = await service.generate_decisions_from_cost(
                user_id,
                cost_record,
                classification,
            )
            
            return {
                'cost_record_id': cost_record_id,
                'decisions_generated': len(decisions),
                'decision_ids': [d.id for d in decisions],
            }
    
    import asyncio
    try:
        return asyncio.run(_generate())
    except Exception as exc:
        try:
            self.retry(exc=exc)
        except Exception:
            return {
                'status': 'failed',
                'error': str(exc),
                'retries_exhausted': True,
            }


@shared_task
def auto_execute_eligible_decisions() -> dict:
    """
    Automatically execute eligible decisions (those marked for auto-execution).
    
    This task should be scheduled to run periodically (e.g., every hour).
    """
    async def _execute():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from datetime import datetime, timezone
            
            from app.modules.decisions.models import Decision
            
            # Find eligible decisions
            result = await db.execute(
                select(Decision).where(
                    Decision.is_automated == True,
                    Decision.approved_at == None,
                    Decision.dismissed_at == None,
                    Decision.executed_at == None,
                )
            )
            eligible = result.scalars().all()
            
            executed = 0
            failed = 0
            
            for decision in eligible:
                try:
                    # Auto-approve
                    decision.approved_at = datetime.now(timezone.utc)
                    decision.approved_by = 'system-auto'
                    
                    # Trigger webhook if configured
                    if decision.webhook_url:
                        from app.modules.decisions.webhooks import WebhookDeliverer
                        deliverer = WebhookDeliverer()
                        await deliverer.deliver_with_retry(decision)
                    
                    # Mark as executed
                    decision.executed_at = datetime.now(timezone.utc)
                    decision.execution_result = 'Auto-executed successfully'
                    
                    executed += 1
                except Exception as e:
                    decision.execution_result = f'Auto-execution failed: {str(e)}'
                    failed += 1
            
            await db.commit()
            
            return {
                'eligible': len(eligible),
                'executed': executed,
                'failed': failed,
            }
    
    import asyncio
    return asyncio.run(_execute())


@shared_task
def retry_failed_webhooks() -> dict:
    """Retry webhook deliveries that failed."""
    async def _retry():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.modules.decisions.models import Decision
            
            # Find decisions with failed webhooks that haven't exhausted retries
            result = await db.execute(
                select(Decision).where(
                    Decision.webhook_status == 'failed',
                    Decision.webhook_attempts < 5,
                    Decision.dismissed_at == None,
                )
            )
            failed = result.scalars().all()
            
            retried = 0
            
            for decision in failed:
                try:
                    from app.modules.decisions.webhooks import WebhookDeliverer
                    deliverer = WebhookDeliverer()
                    await deliverer.deliver_with_retry(decision)
                    retried += 1
                except Exception:
                    pass  # Will be retried again
            
            return {
                'failed_count': len(failed),
                'retried': retried,
            }
    
    import asyncio
    return asyncio.run(_retry())
