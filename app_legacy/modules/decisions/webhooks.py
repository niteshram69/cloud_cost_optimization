"""Webhook delivery system with HMAC signatures and retry logic."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import WebhookDeliveryError
from app.modules.decisions.models import Decision, WebhookLog


class WebhookDeliverer:
    """Handles webhook delivery with signing and retries."""
    
    def __init__(self):
        self.timeout = settings.WEBHOOK_TIMEOUT_SECONDS
        self.max_retries = settings.WEBHOOK_MAX_RETRIES
    
    def _generate_signature(self, payload: bytes, secret: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    def _build_payload(self, decision: Decision) -> dict:
        """Build webhook payload from decision."""
        return {
            'event': 'cost_optimization_recommendation',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'decision': {
                'id': decision.id,
                'recommendation': decision.recommendation,
                'action_type': decision.action_type,
                'confidence': decision.confidence,
                'estimated_savings_monthly': str(decision.estimated_savings_monthly) if decision.estimated_savings_monthly else None,
                'is_automated': decision.is_automated,
                'context': decision.context,
            },
        }
    
    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(settings.WEBHOOK_MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.WEBHOOK_RETRY_BACKOFF_BASE, min=1, max=60),
        reraise=True,
    )
    async def _send_request(
        self,
        url: str,
        payload: bytes,
        signature: str,
    ) -> httpx.Response:
        """Send webhook request with retries."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                content=payload,
                headers={
                    'Content-Type': 'application/json',
                    settings.WEBHOOK_SECRET_HEADER: signature,
                    'X-Webhook-Event': 'cost_optimization_recommendation',
                    'X-Webhook-Version': '1.0',
                },
            )
            response.raise_for_status()
            return response
    
    async def deliver(
        self,
        decision: Decision,
        attempt_number: int = 1,
    ) -> WebhookLog:
        """
        Deliver webhook for a decision.
        
        Returns WebhookLog with delivery results.
        """
        if not decision.webhook_url:
            raise WebhookDeliveryError("No webhook URL configured")
        
        # Build payload
        payload_dict = self._build_payload(decision)
        payload_bytes = json.dumps(payload_dict, default=str).encode('utf-8')
        
        # Generate signature
        secret = decision.webhook_secret or settings.SECRET_KEY
        signature = self._generate_signature(payload_bytes, secret)
        
        # Create log entry
        webhook_log = WebhookLog(
            decision_id=decision.id,
            attempt_number=attempt_number,
            status='pending',
            request_payload=payload_bytes.decode('utf-8'),
            triggered_at=datetime.now(timezone.utc),
        )
        
        start_time = time.time()
        
        try:
            # Send request
            response = await self._send_request(
                decision.webhook_url,
                payload_bytes,
                signature,
            )
            
            # Success
            duration_ms = int((time.time() - start_time) * 1000)
            
            webhook_log.status = 'success'
            webhook_log.status_code = response.status_code
            webhook_log.response_body = response.text[:1000]  # Limit size
            webhook_log.completed_at = datetime.now(timezone.utc)
            webhook_log.duration_ms = duration_ms
            
        except httpx.HTTPStatusError as e:
            # HTTP error (4xx, 5xx)
            duration_ms = int((time.time() - start_time) * 1000)
            
            webhook_log.status = 'failure'
            webhook_log.status_code = e.response.status_code
            webhook_log.error_message = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
            webhook_log.completed_at = datetime.now(timezone.utc)
            webhook_log.duration_ms = duration_ms
            
        except Exception as e:
            # Network or other error
            duration_ms = int((time.time() - start_time) * 1000)
            
            webhook_log.status = 'failure'
            webhook_log.error_message = str(e)[:500]
            webhook_log.completed_at = datetime.now(timezone.utc)
            webhook_log.duration_ms = duration_ms
        
        return webhook_log
    
    async def deliver_with_retry(
        self,
        decision: Decision,
    ) -> list[WebhookLog]:
        """
        Deliver webhook with automatic retries.
        
        Returns list of all delivery attempts.
        """
        logs = []
        
        for attempt in range(1, self.max_retries + 1):
            log = await self.deliver(decision, attempt)
            logs.append(log)
            
            # Update decision status
            decision.webhook_attempts = attempt
            decision.webhook_last_attempt = datetime.now(timezone.utc)
            
            if log.status == 'success':
                decision.webhook_status = 'delivered'
                decision.webhook_error = None
                break
            else:
                decision.webhook_status = 'failed'
                decision.webhook_error = log.error_message
        
        return logs
