from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Plan, User
from backend.app.services.account_service import AccountService
from backend.app.services.billing_service import BillingService
from backend.app.services.canonical_tier_mapping_service import CanonicalTierMappingService


class PlatformBootstrapService:
    def __init__(self, db: Session):
        self.db = db

    def bootstrap(self) -> None:
        account_service = AccountService(self.db)
        account_service.ensure_default_plans()
        CanonicalTierMappingService(self.db).ensure_defaults()

        users = self.db.scalars(select(User)).all()
        for user in users:
            account = account_service.ensure_user_account(user)
            plan = self.db.scalar(select(Plan).where(Plan.id == account.plan_id))
            if not plan:
                continue
            BillingService(self.db).ensure_open_cycle(account=account, plan=plan)
