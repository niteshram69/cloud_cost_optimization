import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import (
    AccountState,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    UserAccount,
)


class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    async def create_razorpay_order(
        self,
        *,
        user: User,
        amount: Decimal,
        currency: str,
        receipt: str,
        invoice_number: str | None,
    ) -> dict[str, Any]:
        paise_amount = int((amount * Decimal("100")).quantize(Decimal("1")))
        payload = {
            "amount": paise_amount,
            "currency": currency,
            "receipt": receipt,
            "notes": {
                "user_id": str(user.id),
                "invoice_number": invoice_number or "",
            },
        }

        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            return {
                "id": f"order_local_{receipt}",
                "amount": paise_amount,
                "currency": currency,
                "receipt": receipt,
            }

        auth_bytes = f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode("utf-8")
        auth_header = base64.b64encode(auth_bytes).decode("utf-8")
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.razorpay.com/v1/orders",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def verify_webhook_signature(self, body: bytes, signature: str | None) -> bool:
        if not settings.razorpay_webhook_secret:
            return True
        if not signature:
            return False
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_razorpay_webhook(self, *, event_type: str, payload: dict[str, Any]) -> Payment:
        entity = payload.get("payload", {})
        payment_entity = entity.get("payment", {}).get("entity", {})
        subscription_entity = entity.get("subscription", {}).get("entity", {})

        notes = payment_entity.get("notes", {}) if isinstance(payment_entity, dict) else {}
        user_id = int(notes.get("user_id", 0) or 0)
        invoice_number = notes.get("invoice_number")
        if not user_id and subscription_entity:
            notes = subscription_entity.get("notes", {})
            user_id = int(notes.get("user_id", 0) or 0)
            invoice_number = notes.get("invoice_number")
        if not user_id:
            raise ValueError("Webhook payload missing user reference")

        user = self.db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError("Webhook user not found")

        invoice = None
        if invoice_number:
            invoice = self.db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number))

        payment_status = self._map_event_to_payment_status(event_type)
        amount_minor = payment_entity.get("amount") or subscription_entity.get("quantity") or 0
        amount = (Decimal(amount_minor) / Decimal("100")) if amount_minor else Decimal("0")
        currency = payment_entity.get("currency") or "INR"
        provider_order_id = payment_entity.get("order_id")
        provider_payment_id = payment_entity.get("id")

        payment = Payment(
            user_id=user.id,
            invoice_id=invoice.id if invoice else None,
            provider=PaymentProvider.RAZORPAY,
            provider_order_id=provider_order_id,
            provider_payment_id=provider_payment_id,
            event_type=event_type,
            status=payment_status,
            amount=amount,
            currency=currency,
            raw_event=payload,
        )
        self.db.add(payment)

        if invoice:
            if payment_status == PaymentStatus.CAPTURED:
                invoice.status = InvoiceStatus.PAID
                invoice.paid_at = datetime.now(UTC)
            elif payment_status == PaymentStatus.FAILED:
                invoice.status = InvoiceStatus.FAILED

        self._upsert_subscription_from_event(user_id=user.id, event_type=event_type, payload=payload)
        self._apply_account_state(user_id=user.id, payment_status=payment_status)

        self.db.commit()
        self.db.refresh(payment)
        return payment

    def _upsert_subscription_from_event(self, *, user_id: int, event_type: str, payload: dict[str, Any]) -> None:
        if not event_type.startswith("subscription."):
            return

        subscription_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        provider_subscription_id = subscription_entity.get("id")
        if not provider_subscription_id:
            return

        account = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user_id))
        if not account:
            return
        plan = self.db.scalar(select(Plan).where(Plan.id == account.plan_id))
        if not plan:
            return

        subscription = self.db.scalar(
            select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
        )
        mapped_status = self._map_event_to_subscription_status(event_type)
        period_start = subscription_entity.get("current_start")
        period_end = subscription_entity.get("current_end")
        start_dt = datetime.fromtimestamp(period_start, tz=UTC) if isinstance(period_start, (int, float)) else None
        end_dt = datetime.fromtimestamp(period_end, tz=UTC) if isinstance(period_end, (int, float)) else None

        if not subscription:
            subscription = Subscription(
                user_id=user_id,
                plan_id=plan.id,
                provider=PaymentProvider.RAZORPAY,
                provider_subscription_id=provider_subscription_id,
                status=mapped_status,
                current_period_start=start_dt,
                current_period_end=end_dt,
                metadata_json=subscription_entity,
            )
            self.db.add(subscription)
            return

        subscription.status = mapped_status
        subscription.current_period_start = start_dt
        subscription.current_period_end = end_dt
        subscription.metadata_json = subscription_entity

    def _apply_account_state(self, *, user_id: int, payment_status: PaymentStatus) -> None:
        account = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user_id))
        if not account:
            return
        if payment_status == PaymentStatus.CAPTURED:
            account.account_state = AccountState.ACTIVE
        elif payment_status == PaymentStatus.FAILED:
            account.account_state = AccountState.PAYMENT_DUE

    def _map_event_to_payment_status(self, event_type: str) -> PaymentStatus:
        mapping = {
            "payment.captured": PaymentStatus.CAPTURED,
            "payment.failed": PaymentStatus.FAILED,
            "payment.refunded": PaymentStatus.REFUNDED,
        }
        return mapping.get(event_type, PaymentStatus.CREATED)

    def _map_event_to_subscription_status(self, event_type: str) -> SubscriptionStatus:
        mapping = {
            "subscription.activated": SubscriptionStatus.ACTIVE,
            "subscription.cancelled": SubscriptionStatus.CANCELLED,
            "subscription.halted": SubscriptionStatus.PAST_DUE,
            "subscription.pending": SubscriptionStatus.TRIALING,
        }
        return mapping.get(event_type, SubscriptionStatus.TRIALING)
