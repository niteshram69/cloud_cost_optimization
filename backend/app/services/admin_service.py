from collections import defaultdict
from decimal import Decimal
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import (
    APIKey,
    BillingCycle,
    BillingCycleStatus,
    IngestedRecord,
    Invoice,
    LoginAudit,
    MigrationJob,
    MigrationStatus,
    Payment,
    Plan,
    Recommendation,
    RecommendationStatus,
    StoragePricingRecord,
    StorageRecord,
    Subscription,
    User,
    UserAccount,
    UsageEvent,
    WebhookEvent,
    WebhookProcessStatus,
)
from backend.app.schemas.dashboard import (
    AdminMetricsResponse,
    AdminMigrationResponse,
    AdminUserResponse,
    ClassificationAccuracyResponse,
    CloudUsageOverview,
    RegionUsagePoint,
    SystemHealthResponse,
)
from backend.app.schemas.platform import (
    APIKeyResponse,
    AdminUserAuthInfo,
    AdminUserBasicProfile,
    AdminUserBillingStatus,
    AdminUserCostInsights,
    AdminUserDecisions,
    AdminUserDetailResponse,
    AdminUserUsageMetrics,
    AdminUserWebhooks,
)
from backend.app.services.public_data_guard import is_public_dataset_user


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    def get_users(self) -> list[AdminUserResponse]:
        users = self.db.scalars(select(User).order_by(User.created_at.desc())).all()
        results: list[AdminUserResponse] = []
        for user in users:
            account = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user.id))
            plan = self.db.scalar(select(Plan).where(Plan.id == account.plan_id)) if account else None
            current_cycle = (
                self.db.scalar(
                    select(BillingCycle).where(
                        BillingCycle.user_id == user.id,
                        BillingCycle.status == BillingCycleStatus.OPEN,
                    )
                )
                if account
                else None
            )
            latest_subscription = self.db.scalar(
                select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
            )
            latest_payment = self.db.scalar(
                select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
            )

            request_count = int(current_cycle.request_count or 0) if current_cycle else 0
            included_quota = int(current_cycle.included_quota or 0) if current_cycle else int(plan.included_requests if plan else 0)
            overage = max(request_count - included_quota, 0)
            estimated = Decimal(current_cycle.total_amount) if current_cycle else Decimal("0.00")

            results.append(
                AdminUserResponse(
                    id=user.id,
                    name=user.name,
                    email=user.email,
                    company_name=user.company_name,
                    cloud_provider=user.cloud_provider.value,
                    role=user.role.value,
                    is_active=user.is_active,
                    account_state=account.account_state.value if account else "TRIAL",
                    plan_code=plan.code.value if plan else "FREE",
                    subscription_status=latest_subscription.status.value if latest_subscription else None,
                    current_cycle_usage=request_count,
                    included_quota=included_quota,
                    overage_usage=overage,
                    estimated_cycle_amount=float(round(estimated, 2)),
                    currency=(current_cycle.currency if current_cycle else (account.billing_currency if account else "USD")),
                    last_payment_status=latest_payment.status.value if latest_payment else None,
                    created_at=user.created_at,
                )
            )
        return results

    def get_admin_metrics(self, api_uptime_seconds: float) -> AdminMetricsResponse:
        usage_rows = self.db.execute(
            select(StorageRecord.provider, StorageRecord.region, func.sum(StorageRecord.storage_cost))
            .group_by(StorageRecord.provider, StorageRecord.region)
        ).all()

        by_provider: dict[str, float] = defaultdict(float)
        by_region: list[RegionUsagePoint] = []
        total_cost = 0.0

        for provider, region, total in usage_rows:
            value = float(total or 0.0)
            total_cost += value
            by_provider[provider.value] += value
            by_region.append(RegionUsagePoint(provider=provider.value, region=region, storage_cost=round(value, 2)))

        avg_confidence, total_classified = self.db.execute(
            select(func.avg(StorageRecord.classification_confidence), func.count(StorageRecord.id))
        ).one()

        high_confidence_count = self.db.scalar(
            select(func.count(StorageRecord.id)).where(StorageRecord.classification_confidence > 0.8)
        )

        active_users = self.db.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
        running_migrations = self.db.scalar(
            select(func.count(MigrationJob.id)).where(MigrationJob.status == MigrationStatus.RUNNING)
        )
        failed_migrations = self.db.scalar(
            select(func.count(MigrationJob.id)).where(MigrationJob.status == MigrationStatus.FAILED)
        )
        latest_pricing_version = self.db.scalar(
            select(StoragePricingRecord.pricing_version)
            .order_by(StoragePricingRecord.effective_date.desc(), StoragePricingRecord.created_at.desc())
            .limit(1)
        )

        return AdminMetricsResponse(
            cloud_usage=CloudUsageOverview(
                total_cost=round(total_cost, 2),
                by_provider={key: round(value, 2) for key, value in by_provider.items()},
                by_region=by_region,
            ),
            classification_accuracy=ClassificationAccuracyResponse(
                average_confidence=round(float(avg_confidence or 0.0), 4),
                high_confidence_count=int(high_confidence_count or 0),
                total_classified=int(total_classified or 0),
            ),
            system_health=SystemHealthResponse(
                active_users=int(active_users or 0),
                running_migrations=int(running_migrations or 0),
                failed_migrations=int(failed_migrations or 0),
                api_uptime_seconds=round(api_uptime_seconds, 2),
                pricing_version=str(latest_pricing_version) if latest_pricing_version else None,
            ),
        )

    def get_migrations(self) -> list[AdminMigrationResponse]:
        rows = self.db.scalars(select(MigrationJob).order_by(MigrationJob.created_at.desc()).limit(250)).all()
        return [
            AdminMigrationResponse(
                id=row.id,
                user_id=row.user_id,
                resource_name=row.resource_name,
                source_provider=row.source_provider.value,
                target_provider=row.target_provider.value,
                status=row.status.value,
                progress_percent=row.progress_percent,
                error_message=row.error_message,
                started_at=row.started_at,
                completed_at=row.completed_at,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def get_user_detail(self, user_id: int) -> AdminUserDetailResponse:
        user = self.db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise LookupError("User not found")

        account = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user.id))
        plan = self.db.scalar(select(Plan).where(Plan.id == account.plan_id)) if account else None
        cycle = (
            self.db.scalar(
                select(BillingCycle)
                .where(BillingCycle.user_id == user.id)
                .order_by(BillingCycle.created_at.desc())
            )
            if account
            else None
        )
        latest_subscription = self.db.scalar(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
        )
        latest_invoice = self.db.scalar(
            select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.created_at.desc())
        )
        latest_payment = self.db.scalar(
            select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
        )
        last_login = self.db.scalar(
            select(LoginAudit).where(LoginAudit.user_id == user.id).order_by(LoginAudit.logged_in_at.desc())
        )

        api_keys = self.db.scalars(select(APIKey).where(APIKey.user_id == user.id).order_by(APIKey.created_at.desc())).all()

        total_api_calls = int(
            self.db.scalar(
                select(func.sum(UsageEvent.request_count)).where(UsageEvent.user_id == user.id)
            )
            or 0
        )
        ingested_records = self.db.scalars(select(IngestedRecord).where(IngestedRecord.user_id == user.id)).all()
        ingested_count = len(ingested_records)
        ingested_bytes_estimate = sum(len(json.dumps(record.raw_payload, separators=(",", ":"))) for record in ingested_records)

        total_storage_cost = float(
            self.db.scalar(select(func.sum(StorageRecord.storage_cost)).where(StorageRecord.user_id == user.id))
            or 0.0
        )
        estimated_savings = float(
            self.db.scalar(select(func.sum(StorageRecord.estimated_savings)).where(StorageRecord.user_id == user.id))
            or 0.0
        )

        rec_total = int(
            self.db.scalar(select(func.count(Recommendation.id)).where(Recommendation.user_id == user.id))
            or 0
        )
        rec_open = int(
            self.db.scalar(
                select(func.count(Recommendation.id)).where(
                    Recommendation.user_id == user.id,
                    Recommendation.status == RecommendationStatus.OPEN,
                )
            )
            or 0
        )
        mig_total = int(
            self.db.scalar(select(func.count(MigrationJob.id)).where(MigrationJob.user_id == user.id))
            or 0
        )
        mig_failed = int(
            self.db.scalar(
                select(func.count(MigrationJob.id)).where(
                    MigrationJob.user_id == user.id,
                    MigrationJob.status == MigrationStatus.FAILED,
                )
            )
            or 0
        )

        webhook_total = int(
            self.db.scalar(select(func.count(WebhookEvent.id)).where(WebhookEvent.user_id == user.id))
            or 0
        )
        webhook_failed = int(
            self.db.scalar(
                select(func.count(WebhookEvent.id)).where(
                    WebhookEvent.user_id == user.id,
                    WebhookEvent.status == WebhookProcessStatus.FAILED,
                )
            )
            or 0
        )
        webhook_latest_at = self.db.scalar(
            select(WebhookEvent.received_at)
            .where(WebhookEvent.user_id == user.id)
            .order_by(WebhookEvent.received_at.desc())
        )

        is_billable = not is_public_dataset_user(user)
        return AdminUserDetailResponse(
            basic_profile=AdminUserBasicProfile(
                user_id=user.id,
                tenant_id=f"tenant-{user.id}",
                name=user.name,
                email=user.email,
                company_name=user.company_name,
                status="ACTIVE" if user.is_active else "INACTIVE",
                role=user.role.value,
                created_at=user.created_at,
            ),
            auth_info=AdminUserAuthInfo(
                last_login_at=last_login.logged_in_at if last_login else None,
                api_keys=[
                    APIKeyResponse(
                        id=item.id,
                        name=item.name,
                        key_prefix=item.key_prefix,
                        scopes=[scope for scope in item.scopes.split(",") if scope],
                        is_active=item.is_active,
                        last_used_at=item.last_used_at,
                        created_at=item.created_at,
                    )
                    for item in api_keys
                ],
            ),
            usage_metrics=AdminUserUsageMetrics(
                total_api_calls=total_api_calls,
                total_data_ingested_records=ingested_count,
                total_data_ingested_bytes_estimate=ingested_bytes_estimate,
                current_cycle_requests=int(cycle.request_count if cycle else 0),
            ),
            cost_insights=AdminUserCostInsights(
                total_storage_cost=round(total_storage_cost, 2),
                estimated_monthly_savings=round(estimated_savings, 2),
                latest_cycle_total_amount=Decimal(cycle.total_amount if cycle else 0),
                overage_usage=int(cycle.overage_count if cycle else 0),
                overage_amount=Decimal(cycle.overage_amount if cycle else 0),
            ),
            decisions_triggered=AdminUserDecisions(
                recommendations_total=rec_total,
                recommendations_open=rec_open,
                migrations_total=mig_total,
                migrations_failed=mig_failed,
            ),
            webhooks_fired=AdminUserWebhooks(
                total_events=webhook_total,
                failed_events=webhook_failed,
                latest_event_at=webhook_latest_at,
            ),
            billing_status=AdminUserBillingStatus(
                plan_code=plan.code.value if plan else "FREE",
                account_state=account.account_state.value if account else "TRIAL",
                subscription_status=latest_subscription.status.value if latest_subscription else None,
                latest_invoice_status=latest_invoice.status.value if latest_invoice else None,
                latest_payment_status=latest_payment.status.value if latest_payment else None,
                payment_enforced=settings.payment_enforcement_enabled,
                is_billable=is_billable,
            ),
        )

    def list_ingested_records(
        self,
        *,
        user_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IngestedRecord]:
        query = select(IngestedRecord).order_by(IngestedRecord.created_at.desc())
        if user_id is not None:
            query = query.where(IngestedRecord.user_id == user_id)
        return self.db.scalars(query.offset(offset).limit(limit)).all()

    def update_ingested_record(
        self,
        *,
        record_id: int,
        external_id: str | None = None,
        schema_version: str | None = None,
        raw_payload: dict | None = None,
        normalized_payload: dict | None = None,
    ) -> IngestedRecord:
        record = self.db.scalar(select(IngestedRecord).where(IngestedRecord.id == record_id))
        if not record:
            raise LookupError("Ingested record not found")

        if external_id is not None:
            record.external_id = external_id
        if schema_version is not None:
            record.schema_version = schema_version
        if raw_payload is not None:
            record.raw_payload = raw_payload
        if normalized_payload is not None:
            record.normalized_payload = normalized_payload
        elif raw_payload is not None:
            record.normalized_payload = {
                "schema_version": record.schema_version,
                "attributes": raw_payload,
            }

        self.db.commit()
        self.db.refresh(record)
        return record

    def delete_ingested_record(self, *, record_id: int) -> None:
        record = self.db.scalar(select(IngestedRecord).where(IngestedRecord.id == record_id))
        if not record:
            raise LookupError("Ingested record not found")
        self.db.delete(record)
        self.db.commit()
