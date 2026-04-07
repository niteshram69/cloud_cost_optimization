from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import AccountState, Plan, PlanCode, User, UserAccount


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_plans(self) -> None:
        defaults = [
            {
                "code": PlanCode.FREE,
                "name": "Free",
                "description": "Starter plan with limited requests and no card required",
                "base_monthly_price": Decimal("0.00"),
                "included_requests": 10_000,
                "overage_price_per_request": Decimal("0.002000"),
            },
            {
                "code": PlanCode.PRO,
                "name": "Pro",
                "description": "Production plan with base fee and predictable overage pricing",
                "base_monthly_price": Decimal("49.00"),
                "included_requests": 100_000,
                "overage_price_per_request": Decimal("0.001000"),
            },
            {
                "code": PlanCode.ENTERPRISE,
                "name": "Enterprise",
                "description": "Custom enterprise plan with negotiated limits and terms",
                "base_monthly_price": Decimal("999.00"),
                "included_requests": 1_000_000,
                "overage_price_per_request": Decimal("0.000500"),
            },
        ]

        existing = {
            plan.code: plan
            for plan in self.db.scalars(select(Plan).where(Plan.code.in_([PlanCode.FREE, PlanCode.PRO, PlanCode.ENTERPRISE])))
        }
        changed = False
        for entry in defaults:
            plan = existing.get(entry["code"])
            if not plan:
                plan = Plan(
                    code=entry["code"],
                    name=entry["name"],
                    description=entry["description"],
                    base_monthly_price=entry["base_monthly_price"],
                    included_requests=entry["included_requests"],
                    overage_price_per_request=entry["overage_price_per_request"],
                    currency=settings.default_currency,
                    is_active=True,
                )
                self.db.add(plan)
                changed = True
                continue

            plan.name = entry["name"]
            plan.description = entry["description"]
            plan.base_monthly_price = entry["base_monthly_price"]
            plan.included_requests = entry["included_requests"]
            plan.overage_price_per_request = entry["overage_price_per_request"]
            plan.currency = settings.default_currency
            plan.is_active = True
            changed = True

        if changed:
            self.db.commit()

    def get_plan(self, code: PlanCode) -> Plan:
        plan = self.db.scalar(select(Plan).where(Plan.code == code))
        if not plan:
            raise ValueError(f"Plan {code.value} is not configured")
        return plan

    def ensure_user_account(self, user: User) -> UserAccount:
        account = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user.id))
        if account:
            return account

        default_plan_code = PlanCode.PRO if user.role.value == "ADMIN" else PlanCode.FREE
        plan = self.get_plan(default_plan_code)
        now = datetime.now(UTC)
        account = UserAccount(
            user_id=user.id,
            plan_id=plan.id,
            account_state=AccountState.TRIAL if default_plan_code != PlanCode.ENTERPRISE else AccountState.ACTIVE,
            billing_currency=plan.currency,
            billing_region=settings.default_region,
            trial_ends_at=now + timedelta(days=settings.trial_days),
            grace_period_ends_at=now + timedelta(days=settings.payment_grace_days),
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def ensure_accounts_for_all_users(self) -> None:
        users = self.db.scalars(select(User)).all()
        for user in users:
            self.ensure_user_account(user)
