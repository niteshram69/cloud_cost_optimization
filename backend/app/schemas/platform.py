from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from backend.app.models.enums import AccountState, IngestionMethod, InvoiceStatus, PaymentStatus, PlanCode, SubscriptionStatus


class APIKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["data:read", "data:write", "usage:read"])


class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class APIKeyCreateResponse(APIKeyResponse):
    api_key: str


class DataCreateRequest(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any]
    schema_version: str = Field(default="v1", max_length=32)


class IngestionEventRequest(BaseModel):
    source_type: str = Field(min_length=2, max_length=64)
    resource_id: str = Field(min_length=1, max_length=255)
    timestamp: datetime
    usage_metrics: dict[str, Any] = Field(default_factory=dict)
    cost_metrics: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=128)


class IngestionEventResponse(BaseModel):
    record_id: int
    status: str
    ingestion_method: IngestionMethod
    created_at: datetime


class IngestionUploadResponse(BaseModel):
    job_id: int
    status: str
    file_name: str
    data_origin: str
    is_billable: bool
    message: str


class IngestionJobStatusResponse(BaseModel):
    job_id: int
    status: str
    file_name: str | None
    source_type: str
    record_count: int
    error_message: str | None
    data_origin: str
    is_billable: bool
    created_at: datetime
    updated_at: datetime


class AdminIngestedRecordResponse(BaseModel):
    id: int
    user_id: int
    data_source_id: int | None
    ingestion_method: IngestionMethod
    schema_version: str
    external_id: str | None
    lineage_ref: str
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]
    created_at: datetime
    processed_at: datetime | None


class AdminIngestedRecordUpdateRequest(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    schema_version: str | None = Field(default=None, max_length=32)
    raw_payload: dict[str, Any] | None = None
    normalized_payload: dict[str, Any] | None = None


class IntegrationConnectRequest(BaseModel):
    provider: str = Field(pattern="^(AWS|GCP|AZURE)$")
    source_name: str = Field(min_length=2, max_length=120)
    endpoint_url: str = Field(min_length=10, max_length=500)
    auth_type: str = Field(default="api_key", min_length=2, max_length=32)
    credentials: dict[str, str] = Field(default_factory=dict)
    sync_interval_minutes: int = Field(default=60, ge=5, le=1440)
    is_read_only: bool = True


class IntegrationConnectResponse(BaseModel):
    integration_id: int
    provider: str
    source_name: str
    status: str
    sync_interval_minutes: int
    is_read_only: bool
    created_at: datetime


class IntegrationSyncRequest(BaseModel):
    integration_id: int = Field(gt=0)
    incremental_cursor: str | None = None
    estimated_cost_per_call: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))


class IntegrationSyncResponse(BaseModel):
    integration_id: int
    provider: str
    source_name: str
    records_ingested: int
    next_cursor: str | None
    total_ingestion_cost: Decimal
    status: str


class IntegrationStatusResponse(BaseModel):
    integration_id: int
    provider: str
    source_name: str
    status: str
    last_synced_at: datetime | None
    sync_cursor: str | None
    sync_interval_minutes: int
    is_read_only: bool


class DataRecordResponse(BaseModel):
    id: int
    user_id: int
    ingestion_method: IngestionMethod
    schema_version: str
    external_id: str | None
    lineage_ref: str
    normalized_payload: dict[str, Any]
    created_at: datetime


class DataListResponse(BaseModel):
    items: list[DataRecordResponse]
    page: int
    page_size: int
    total: int


class UsageSummaryResponse(BaseModel):
    user_id: int
    api_key_id: int | None
    cycle_start: datetime
    cycle_end: datetime
    request_count: int
    data_volume_bytes: int
    compute_units: int


class BillingPreviewResponse(BaseModel):
    user_id: int
    plan_code: PlanCode
    account_state: AccountState
    cycle_start: datetime
    cycle_end: datetime
    included_quota: int
    usage_count: int
    overage_count: int
    base_amount: Decimal
    overage_amount: Decimal
    total_amount: Decimal
    currency: str


class InvoiceResponse(BaseModel):
    invoice_number: str
    status: InvoiceStatus
    amount: Decimal
    currency: str
    issued_at: datetime | None
    due_at: datetime | None


class BillingResponse(BaseModel):
    current_cycle: BillingPreviewResponse
    latest_invoices: list[InvoiceResponse]


class OfficialSyncRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    provider: str = Field(min_length=2, max_length=64)
    endpoint_url: str = Field(min_length=10, max_length=500)
    auth_type: str = Field(default="api_key", max_length=32)
    auth_token: str | None = None
    incremental_cursor: str | None = None
    estimated_cost_per_call: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))


class OfficialSyncResponse(BaseModel):
    source_id: int
    provider: str
    records_ingested: int
    next_cursor: str | None
    total_ingestion_cost: Decimal


class FileIngestionResponse(BaseModel):
    ingested_count: int
    failed_count: int
    errors: list[str]


class WebhookAckResponse(BaseModel):
    event_id: str
    status: str


class RazorpayOrderRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="INR", max_length=8)
    receipt: str = Field(min_length=3, max_length=64)
    invoice_number: str | None = Field(default=None, max_length=64)


class RazorpayOrderResponse(BaseModel):
    order_id: str
    amount: Decimal
    currency: str
    receipt: str


class RazorpayWebhookResponse(BaseModel):
    processed: bool
    event_type: str
    payment_status: PaymentStatus


class AdminUserFinancialResponse(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    company_name: str
    plan_code: PlanCode
    account_state: AccountState
    subscription_status: SubscriptionStatus | None
    current_cycle_usage: int
    included_quota: int
    overage_usage: int
    estimated_cycle_amount: Decimal
    currency: str


class PublicDatasetSourceResponse(BaseModel):
    key: str
    source_name: str
    description: str
    provider_hint: str
    format: str
    is_billable: bool = False


class PublicDatasetIngestRequest(BaseModel):
    source_key: str
    limit: int = Field(default=500, ge=1, le=5000)


class PublicDatasetIngestResponse(BaseModel):
    source_key: str
    source_name: str
    tenant_id: int
    inserted_records: int
    skipped_records: int
    is_billable: bool


class BillingExportIngestRequest(BaseModel):
    user_id: int = Field(gt=0)
    provider: str = Field(pattern="^(AWS|GCP)$")
    source_type: str = Field(pattern="^(AWS_CUR|GCP_BQ_EXPORT)$")
    source_ref: str = Field(min_length=3, max_length=512)
    rows: list[dict[str, Any]] = Field(default_factory=list, min_length=1, max_length=100000)
    idempotency_key: str | None = Field(default=None, max_length=128)
    window_start: datetime | None = None
    window_end: datetime | None = None
    dry_run: bool = False


class BillingExportIngestResponse(BaseModel):
    run_id: int
    provider: str
    source_type: str
    status: str
    source_ref: str
    idempotency_key: str
    records_seen: int
    records_inserted: int
    skipped_non_storage: int
    window_start: datetime | None
    window_end: datetime | None
    started_at: datetime
    completed_at: datetime | None


class BillingPlanCardResponse(BaseModel):
    code: str
    name: str
    monthly_price: Decimal
    included_requests: int
    overage_price_per_request: Decimal
    features: list[str]
    cta: str


class BillingOverviewResponse(BaseModel):
    plan_code: str
    account_state: str
    usage_count: int
    included_quota: int
    usage_percent: float
    payment_enforcement_enabled: bool
    upgrade_cta: str
    contact_sales_cta: str


class BillingCatalogResponse(BaseModel):
    plans: list[BillingPlanCardResponse]
    faq: list[dict[str, str]]
    payment_enforcement_enabled: bool


class AdminUserBasicProfile(BaseModel):
    user_id: int
    tenant_id: str
    name: str
    email: str
    company_name: str
    status: str
    role: str
    created_at: datetime


class AdminUserAuthInfo(BaseModel):
    last_login_at: datetime | None
    api_keys: list[APIKeyResponse]


class AdminUserUsageMetrics(BaseModel):
    total_api_calls: int
    total_data_ingested_records: int
    total_data_ingested_bytes_estimate: int
    current_cycle_requests: int


class AdminUserCostInsights(BaseModel):
    total_storage_cost: float
    estimated_monthly_savings: float
    latest_cycle_total_amount: Decimal
    overage_usage: int
    overage_amount: Decimal


class AdminUserDecisions(BaseModel):
    recommendations_total: int
    recommendations_open: int
    migrations_total: int
    migrations_failed: int


class AdminUserWebhooks(BaseModel):
    total_events: int
    failed_events: int
    latest_event_at: datetime | None


class AdminUserBillingStatus(BaseModel):
    plan_code: str
    account_state: str
    subscription_status: str | None
    latest_invoice_status: str | None
    latest_payment_status: str | None
    payment_enforced: bool
    is_billable: bool


class AdminUserDetailResponse(BaseModel):
    basic_profile: AdminUserBasicProfile
    auth_info: AdminUserAuthInfo
    usage_metrics: AdminUserUsageMetrics
    cost_insights: AdminUserCostInsights
    decisions_triggered: AdminUserDecisions
    webhooks_fired: AdminUserWebhooks
    billing_status: AdminUserBillingStatus
