from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import (
    AccountState,
    BillingCycle,
    BillingCycleStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    UserAccount,
)
from backend.app.schemas.platform import BillingPreviewResponse, BillingResponse, InvoiceResponse
from backend.app.services.public_data_guard import is_public_dataset_user


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_open_cycle(self, account: UserAccount, plan: Plan) -> BillingCycle:
        now = datetime.now(UTC)
        current = self.db.scalar(
            select(BillingCycle).where(
                BillingCycle.user_id == account.user_id,
                BillingCycle.status == BillingCycleStatus.OPEN,
                BillingCycle.starts_at <= now,
                BillingCycle.ends_at > now,
            )
        )
        if current:
            return current

        starts_at = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Move to next month start.
        if starts_at.month == 12:
            next_month = starts_at.replace(year=starts_at.year + 1, month=1)
        else:
            next_month = starts_at.replace(month=starts_at.month + 1)

        cycle = BillingCycle(
            user_id=account.user_id,
            plan_id=plan.id,
            starts_at=starts_at,
            ends_at=next_month,
            status=BillingCycleStatus.OPEN,
            included_quota=plan.included_requests,
            request_count=0,
            overage_count=0,
            base_amount=plan.base_monthly_price,
            overage_amount=Decimal("0.00"),
            total_amount=plan.base_monthly_price,
            currency=account.billing_currency,
        )
        self.db.add(cycle)
        self.db.commit()
        self.db.refresh(cycle)
        return cycle

    def billing_preview(self, *, user: User, account: UserAccount, plan: Plan) -> BillingPreviewResponse:
        if is_public_dataset_user(user):
            cycle = self.ensure_open_cycle(account=account, plan=plan)
            cycle.request_count = 0
            cycle.overage_count = 0
            cycle.base_amount = Decimal("0.00")
            cycle.overage_amount = Decimal("0.00")
            cycle.total_amount = Decimal("0.00")
            self.db.commit()
            return BillingPreviewResponse(
                user_id=user.id,
                plan_code=plan.code,
                account_state=account.account_state,
                cycle_start=cycle.starts_at,
                cycle_end=cycle.ends_at,
                included_quota=cycle.included_quota,
                usage_count=0,
                overage_count=0,
                base_amount=Decimal("0.00"),
                overage_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                currency=cycle.currency,
            )

        cycle = self.ensure_open_cycle(account=account, plan=plan)
        usage = int(cycle.request_count or 0)
        overage = max(usage - cycle.included_quota, 0)
        overage_amount = Decimal(overage) * Decimal(plan.overage_price_per_request)
        total_amount = Decimal(plan.base_monthly_price) + overage_amount
        cycle.overage_count = overage
        cycle.overage_amount = overage_amount
        cycle.total_amount = total_amount
        self.db.commit()

        self.apply_account_state(account=account)

        return BillingPreviewResponse(
            user_id=user.id,
            plan_code=plan.code,
            account_state=account.account_state,
            cycle_start=cycle.starts_at,
            cycle_end=cycle.ends_at,
            included_quota=cycle.included_quota,
            usage_count=usage,
            overage_count=overage,
            base_amount=Decimal(cycle.base_amount),
            overage_amount=Decimal(cycle.overage_amount),
            total_amount=Decimal(cycle.total_amount),
            currency=cycle.currency,
        )

    def billing_with_invoices(self, *, user: User, account: UserAccount, plan: Plan) -> BillingResponse:
        preview = self.billing_preview(user=user, account=account, plan=plan)
        invoices = self.db.scalars(
            select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.created_at.desc()).limit(12)
        ).all()
        return BillingResponse(
            current_cycle=preview,
            latest_invoices=[
                InvoiceResponse(
                    invoice_number=item.invoice_number,
                    status=item.status,
                    amount=Decimal(item.amount),
                    currency=item.currency,
                    issued_at=item.issued_at,
                    due_at=item.due_at,
                )
                for item in invoices
            ],
        )

    def close_cycle_and_generate_invoice(self, *, account: UserAccount, plan: Plan) -> Invoice:
        user = self.db.scalar(select(User).where(User.id == account.user_id))
        if user and is_public_dataset_user(user):
            raise ValueError("Public dataset tenants are non-billable")

        cycle = self.ensure_open_cycle(account=account, plan=plan)
        usage = int(cycle.request_count or 0)
        overage = max(usage - cycle.included_quota, 0)
        overage_amount = Decimal(overage) * Decimal(plan.overage_price_per_request)
        total_amount = Decimal(plan.base_monthly_price) + overage_amount

        cycle.overage_count = overage
        cycle.overage_amount = overage_amount
        cycle.total_amount = total_amount
        cycle.status = BillingCycleStatus.CLOSED

        invoice_number = f"INV-{account.user_id}-{cycle.starts_at.strftime('%Y%m')}"
        invoice = self.db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number))
        if not invoice:
            invoice = Invoice(
                user_id=account.user_id,
                billing_cycle_id=cycle.id,
                invoice_number=invoice_number,
                status=InvoiceStatus.ISSUED,
                amount=total_amount,
                currency=cycle.currency,
                issued_at=datetime.now(UTC),
                due_at=datetime.now(UTC) + timedelta(days=settings.payment_grace_days),
            )
            self.db.add(invoice)
        else:
            invoice.amount = total_amount
            invoice.currency = cycle.currency
            invoice.status = InvoiceStatus.ISSUED
            invoice.issued_at = datetime.now(UTC)
            invoice.due_at = datetime.now(UTC) + timedelta(days=settings.payment_grace_days)

        cycle.status = BillingCycleStatus.INVOICED
        self.db.commit()
        self.db.refresh(invoice)
        self.apply_account_state(account=account)
        return invoice

    def apply_account_state(self, *, account: UserAccount) -> AccountState:
        now = datetime.now(UTC)

        latest_subscription = self.db.scalar(
            select(Subscription)
            .where(Subscription.user_id == account.user_id)
            .order_by(Subscription.created_at.desc())
        )
        if latest_subscription and latest_subscription.status == SubscriptionStatus.CANCELLED:
            account.account_state = AccountState.CANCELLED
            self.db.commit()
            return account.account_state

        latest_failed_payment = self.db.scalar(
            select(Payment)
            .where(Payment.user_id == account.user_id, Payment.status == PaymentStatus.FAILED)
            .order_by(Payment.created_at.desc())
        )

        unpaid_invoice = self.db.scalar(
            select(Invoice)
            .where(
                Invoice.user_id == account.user_id,
                Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.FAILED]),
            )
            .order_by(Invoice.created_at.desc())
        )

        if unpaid_invoice and unpaid_invoice.due_at and unpaid_invoice.due_at < now:
            account.account_state = AccountState.SUSPENDED
        elif latest_failed_payment:
            account.account_state = AccountState.PAYMENT_DUE
        elif account.trial_ends_at and account.trial_ends_at > now:
            account.account_state = AccountState.TRIAL
        else:
            account.account_state = AccountState.ACTIVE

        self.db.commit()
        return account.account_state

    def enforce_account_access(self, account: UserAccount) -> None:
        if not settings.payment_enforcement_enabled:
            return
        if account.account_state in {AccountState.SUSPENDED, AccountState.CANCELLED}:
            raise ValueError(f"Account is {account.account_state.value}. API access denied")

    def latest_payment_status(self, user_id: int) -> PaymentStatus | None:
        status = self.db.scalar(
            select(Payment.status).where(Payment.user_id == user_id).order_by(Payment.created_at.desc())
        )
        return status

    def usage_total_for_cycle(self, user_id: int, cycle: BillingCycle) -> int:
        value = self.db.scalar(
            select(func.sum(BillingCycle.request_count)).where(BillingCycle.id == cycle.id, BillingCycle.user_id == user_id)
        )
        return int(value or cycle.request_count or 0)
