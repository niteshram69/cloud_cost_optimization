import hmac
import hashlib
import json
from pathlib import Path
import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import APIPrincipal, get_api_principal, get_current_user, require_role
from backend.app.core.config import settings
from backend.app.core.crypto import decrypt_credentials, encrypt_credentials
from backend.app.database import get_db
from backend.app.models import (
    BillingCycle,
    BillingCycleStatus,
    DataSource,
    DataSourceType,
    IngestedRecord,
    IngestionJob,
    IngestionMethod,
    Plan,
    User,
    UserAccount,
    UserRole,
    WebhookProcessStatus,
)
from backend.app.schemas.platform import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    BillingCatalogResponse,
    BillingOverviewResponse,
    BillingPlanCardResponse,
    BillingResponse,
    DataCreateRequest,
    DataListResponse,
    DataRecordResponse,
    FileIngestionResponse,
    IngestionEventRequest,
    IngestionEventResponse,
    IngestionJobStatusResponse,
    IngestionUploadResponse,
    IntegrationConnectRequest,
    IntegrationConnectResponse,
    IntegrationStatusResponse,
    IntegrationSyncRequest,
    IntegrationSyncResponse,
    OfficialSyncRequest,
    OfficialSyncResponse,
    PublicDatasetIngestRequest,
    PublicDatasetIngestResponse,
    PublicDatasetSourceResponse,
    RazorpayOrderRequest,
    RazorpayOrderResponse,
    RazorpayWebhookResponse,
    UsageSummaryResponse,
    WebhookAckResponse,
)
from backend.app.services.api_key_service import APIKeyService
from backend.app.services.billing_service import BillingService
from backend.app.services.ingestion_service import IngestionService
from backend.app.services.payment_service import PaymentService
from backend.app.services.public_dataset_service import PublicDatasetService
from backend.app.services.usage_service import UsageService

router = APIRouter(tags=["platform"])
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads"


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload.json").name
    return name or "upload.json"


def _run_upload_job_inline(job_id: int, file_path: str) -> None:
    from backend.app.workers.tasks import process_ingestion_upload_job

    process_ingestion_upload_job(job_id=job_id, file_path=file_path)


def _enqueue_upload_job(job_id: int, file_path: str) -> None:
    if not settings.ingestion_use_celery:
        _run_upload_job_inline(job_id=job_id, file_path=file_path)
        return
    try:
        from backend.app.workers.tasks import process_ingestion_upload_job

        process_ingestion_upload_job.delay(job_id, file_path)
    except Exception:
        _run_upload_job_inline(job_id=job_id, file_path=file_path)


def _dispatch_upload_job_detached(job_id: int, file_path: str) -> None:
    thread = threading.Thread(
        target=_enqueue_upload_job,
        args=(job_id, file_path),
        daemon=True,
        name=f"ingestion-job-{job_id}",
    )
    thread.start()


def _serialize_api_key(item) -> APIKeyResponse:
    return APIKeyResponse(
        id=item.id,
        name=item.name,
        key_prefix=item.key_prefix,
        scopes=[scope for scope in item.scopes.split(",") if scope],
        is_active=item.is_active,
        last_used_at=item.last_used_at,
        created_at=item.created_at,
    )


@router.post("/api/keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIKeyCreateResponse:
    service = APIKeyService(db)
    key, raw_key = service.create_key(user=current_user, name=payload.name, scopes=payload.scopes)
    serialized = _serialize_api_key(key)
    return APIKeyCreateResponse(**serialized.model_dump(), api_key=raw_key)


@router.get("/api/keys", response_model=list[APIKeyResponse])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[APIKeyResponse]:
    service = APIKeyService(db)
    return [_serialize_api_key(item) for item in service.list_user_keys(current_user.id)]


@router.post("/api/keys/{api_key_id}/revoke", response_model=APIKeyResponse)
def revoke_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIKeyResponse:
    service = APIKeyService(db)
    try:
        key = service.revoke_key(user_id=current_user.id, api_key_id=api_key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _serialize_api_key(key)


@router.post(
    "/api/v1/ingestion/upload",
    response_model=IngestionUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_ingestion_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestionUploadResponse:
    filename = _safe_upload_name(file.filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    ingestion = IngestionService(db)
    validation_errors = ingestion.validate_file_schema(filename=filename, content=content)
    if validation_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation_errors[0])

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{filename}"
    stored_path = UPLOAD_DIR / stored_name
    stored_path.write_bytes(content)

    job = IngestionJob(
        user_id=current_user.id,
        uploaded_by=current_user.email,
        file_name=filename,
        source_type="MANUAL_UPLOAD",
        status="PENDING",
        data_origin="USER_UPLOAD",
        is_billable=True,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _dispatch_upload_job_detached(job.id, str(stored_path))

    UsageService(db).track_request(
        user_id=current_user.id,
        api_key_id=None,
        endpoint="/api/v1/ingestion/upload",
        method="POST",
        data_volume_bytes=len(content),
        compute_units=1,
    )

    return IngestionUploadResponse(
        job_id=job.id,
        status=job.status,
        file_name=filename,
        data_origin=job.data_origin,
        is_billable=bool(job.is_billable),
        message="Upload accepted and queued for asynchronous processing.",
    )


@router.get("/api/v1/ingestion/jobs", response_model=list[IngestionJobStatusResponse])
def list_ingestion_jobs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[IngestionJobStatusResponse]:
    rows = db.scalars(
        select(IngestionJob)
        .where(IngestionJob.user_id == current_user.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(limit)
    ).all()
    return [
        IngestionJobStatusResponse(
            job_id=row.id,
            status=row.status,
            file_name=row.file_name,
            source_type=row.source_type,
            record_count=row.record_count,
            error_message=row.error_message,
            data_origin=row.data_origin,
            is_billable=bool(row.is_billable),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/api/v1/ingestion/jobs/{job_id}", response_model=IngestionJobStatusResponse)
def get_ingestion_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestionJobStatusResponse:
    row = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.user_id == current_user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")
    return IngestionJobStatusResponse(
        job_id=row.id,
        status=row.status,
        file_name=row.file_name,
        source_type=row.source_type,
        record_count=row.record_count,
        error_message=row.error_message,
        data_origin=row.data_origin,
        is_billable=bool(row.is_billable),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/api/v1/ingestion/events", response_model=IngestionEventResponse, status_code=status.HTTP_201_CREATED)
def ingest_programmatic_event(
    payload: IngestionEventRequest,
    principal: APIPrincipal = Depends(get_api_principal),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
) -> IngestionEventResponse:
    idempotency_key = payload.idempotency_key or x_idempotency_key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency key is required in payload or X-Idempotency-Key header",
        )

    event_payload = {
        "source_type": payload.source_type,
        "resource_id": payload.resource_id,
        "timestamp": payload.timestamp.isoformat(),
        "usage_metrics": payload.usage_metrics,
        "cost_metrics": payload.cost_metrics,
        "attributes": payload.attributes,
        "metadata": {
            "data_origin": "USER_API",
            "is_billable": True,
        },
    }

    ingestion = IngestionService(db)
    try:
        record = ingestion.ingest_user_payload(
            user=principal.user,
            api_key=principal.api_key,
            payload=event_payload,
            schema_version="v1",
            external_id=payload.resource_id,
            idempotency_key=idempotency_key,
            method=IngestionMethod.USER_REST,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/api/v1/ingestion/events",
        method="POST",
        data_volume_bytes=len(json.dumps(event_payload)),
        compute_units=1,
        idempotency_key=idempotency_key,
    )
    return IngestionEventResponse(
        record_id=record.id,
        status="READY",
        ingestion_method=record.ingestion_method,
        created_at=record.created_at,
    )


@router.post(
    "/api/v2/integrations/connect",
    response_model=IntegrationConnectResponse,
    status_code=status.HTTP_201_CREATED,
)
def connect_official_integration(
    payload: IntegrationConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationConnectResponse:
    encrypted_credentials = encrypt_credentials(payload.credentials)
    auth_config = {
        "auth_type": payload.auth_type,
        "endpoint_url": payload.endpoint_url,
        "encrypted_credentials": encrypted_credentials,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "is_read_only": payload.is_read_only,
    }

    source = db.scalar(
        select(DataSource).where(
            DataSource.user_id == current_user.id,
            DataSource.source_type == DataSourceType.OFFICIAL_API,
            DataSource.provider == payload.provider,
            DataSource.name == payload.source_name,
        )
    )
    if source:
        source.auth_config = auth_config
        source.status = "ACTIVE"
    else:
        source = DataSource(
            user_id=current_user.id,
            source_type=DataSourceType.OFFICIAL_API,
            provider=payload.provider,
            name=payload.source_name,
            auth_config=auth_config,
            status="ACTIVE",
        )
        db.add(source)

    db.commit()
    db.refresh(source)
    return IntegrationConnectResponse(
        integration_id=source.id,
        provider=source.provider,
        source_name=source.name,
        status=source.status,
        sync_interval_minutes=int(auth_config["sync_interval_minutes"]),
        is_read_only=bool(auth_config["is_read_only"]),
        created_at=source.created_at,
    )


@router.post("/api/v2/integrations/sync", response_model=IntegrationSyncResponse, status_code=status.HTTP_202_ACCEPTED)
async def sync_integration(
    payload: IntegrationSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationSyncResponse:
    source = db.scalar(
        select(DataSource).where(
            DataSource.id == payload.integration_id,
            DataSource.user_id == current_user.id,
            DataSource.source_type == DataSourceType.OFFICIAL_API,
        )
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    auth_config = source.auth_config or {}
    endpoint_url = str(auth_config.get("endpoint_url") or "").strip()
    if not endpoint_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Integration endpoint URL is missing")

    credentials = decrypt_credentials(auth_config.get("encrypted_credentials"))
    auth_token = (
        credentials.get("access_token")
        or credentials.get("api_key")
        or credentials.get("token")
        or credentials.get("bearer_token")
    )

    service = IngestionService(db)
    try:
        synced_source, records, next_cursor, total_cost = await service.sync_official_api_source(
            user=current_user,
            source_name=source.name,
            provider=source.provider,
            endpoint_url=endpoint_url,
            auth_type=str(auth_config.get("auth_type", "api_key")),
            auth_token=str(auth_token) if auth_token else None,
            incremental_cursor=payload.incremental_cursor or source.sync_cursor,
            estimated_cost_per_call=payload.estimated_cost_per_call,
        )
    except Exception as exc:
        source.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Integration sync failed: {exc}") from exc

    synced_source.status = "ACTIVE"
    db.commit()
    db.refresh(synced_source)

    UsageService(db).track_request(
        user_id=current_user.id,
        api_key_id=None,
        endpoint="/api/v2/integrations/sync",
        method="POST",
        data_volume_bytes=0,
        compute_units=max(1, len(records)),
    )
    return IntegrationSyncResponse(
        integration_id=synced_source.id,
        provider=synced_source.provider,
        source_name=synced_source.name,
        records_ingested=len(records),
        next_cursor=next_cursor,
        total_ingestion_cost=Decimal(total_cost),
        status=synced_source.status,
    )


@router.get("/api/v2/integrations/status", response_model=list[IntegrationStatusResponse])
def integration_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IntegrationStatusResponse]:
    sources = db.scalars(
        select(DataSource)
        .where(
            DataSource.user_id == current_user.id,
            DataSource.source_type == DataSourceType.OFFICIAL_API,
        )
        .order_by(DataSource.created_at.desc())
    ).all()
    return [
        IntegrationStatusResponse(
            integration_id=source.id,
            provider=source.provider,
            source_name=source.name,
            status=source.status,
            last_synced_at=source.last_synced_at,
            sync_cursor=source.sync_cursor,
            sync_interval_minutes=int((source.auth_config or {}).get("sync_interval_minutes", 60)),
            is_read_only=bool((source.auth_config or {}).get("is_read_only", True)),
        )
        for source in sources
    ]


@router.post("/api/ingestion/official/sync", response_model=OfficialSyncResponse)
async def official_sync(
    payload: OfficialSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfficialSyncResponse:
    service = IngestionService(db)
    source, records, next_cursor, total_cost = await service.sync_official_api_source(
        user=current_user,
        source_name=payload.source_name,
        provider=payload.provider,
        endpoint_url=payload.endpoint_url,
        auth_type=payload.auth_type,
        auth_token=payload.auth_token,
        incremental_cursor=payload.incremental_cursor,
        estimated_cost_per_call=payload.estimated_cost_per_call,
    )
    return OfficialSyncResponse(
        source_id=source.id,
        provider=source.provider,
        records_ingested=len(records),
        next_cursor=next_cursor,
        total_ingestion_cost=Decimal(total_cost),
    )


@router.get("/api/admin/public-datasets/sources", response_model=list[PublicDatasetSourceResponse])
def list_public_dataset_sources(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> list[PublicDatasetSourceResponse]:
    service = PublicDatasetService(db)
    return [
        PublicDatasetSourceResponse(
            key=item.key,
            source_name=item.source_name,
            description=item.description,
            provider_hint=item.provider_hint.value,
            format=item.format,
            is_billable=False,
        )
        for item in service.list_sources()
    ]


@router.post(
    "/api/admin/public-datasets/ingest",
    response_model=PublicDatasetIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_public_dataset(
    payload: PublicDatasetIngestRequest,
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> PublicDatasetIngestResponse:
    service = PublicDatasetService(db)
    try:
        result = await service.ingest(source_key=payload.source_key, limit=payload.limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PublicDatasetIngestResponse(**result)


@router.get("/api/billing/overview", response_model=BillingOverviewResponse)
def billing_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingOverviewResponse:
    account = db.scalar(select(UserAccount).where(UserAccount.user_id == current_user.id))
    plan = db.scalar(select(Plan).where(Plan.id == account.plan_id)) if account else None
    cycle = (
        db.scalar(
            select(BillingCycle)
            .where(BillingCycle.user_id == current_user.id, BillingCycle.status == BillingCycleStatus.OPEN)
            .order_by(BillingCycle.created_at.desc())
        )
        if account
        else None
    )
    included = int(cycle.included_quota if cycle else (plan.included_requests if plan else 10_000))
    usage = int(cycle.request_count if cycle else 0)
    usage_percent = round((usage / included) * 100, 2) if included else 0.0
    return BillingOverviewResponse(
        plan_code=plan.code.value if plan else "FREE",
        account_state=(account.account_state.value if account else "TRIAL"),
        usage_count=usage,
        included_quota=included,
        usage_percent=min(100.0, usage_percent),
        payment_enforcement_enabled=settings.payment_enforcement_enabled,
        upgrade_cta="Upgrade (Coming Soon)",
        contact_sales_cta="Contact Sales",
    )


@router.get("/api/billing/catalog", response_model=BillingCatalogResponse)
def billing_catalog(db: Session = Depends(get_db)) -> BillingCatalogResponse:
    plans = db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id.asc())).all()
    cards = [
        BillingPlanCardResponse(
            code=plan.code.value,
            name=plan.name,
            monthly_price=Decimal(plan.base_monthly_price),
            included_requests=plan.included_requests,
            overage_price_per_request=Decimal(plan.overage_price_per_request),
            features=[
                f"{plan.included_requests:,} included API calls",
                f"Overage ${Decimal(plan.overage_price_per_request):,.6f} per API call",
                "Enterprise-grade audit logging",
                "Non-blocking upgrade path",
            ],
            cta="Upgrade (Coming Soon)" if plan.code.value != "ENTERPRISE" else "Contact Sales",
        )
        for plan in plans
    ]
    faq = [
        {"q": "Are payments enforced right now?", "a": "No. Billing UI is visible but usage is not blocked."},
        {"q": "Can I upgrade now?", "a": "Upgrade is currently preview-only; contact sales for early access."},
        {"q": "Will public datasets be billed?", "a": "No. Public dataset records are always non-billable."},
    ]
    return BillingCatalogResponse(
        plans=cards,
        faq=faq,
        payment_enforcement_enabled=settings.payment_enforcement_enabled,
    )


@router.post("/api/admin/usage/flush")
def flush_usage_counters(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    flushed = UsageService(db).flush_redis_aggregates()
    return {"flushed": flushed}


@router.post("/api/admin/billing/close-cycles")
def close_billing_cycles(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    now = datetime.now(UTC)
    cycles = db.execute(
        select(UserAccount, Plan)
        .join(Plan, Plan.id == UserAccount.plan_id)
    ).all()
    closed = 0
    for account, plan in cycles:
        billing = BillingService(db)
        cycle = billing.ensure_open_cycle(account=account, plan=plan)
        if cycle.ends_at <= now:
            try:
                billing.close_cycle_and_generate_invoice(account=account, plan=plan)
                closed += 1
            except ValueError:
                # Public dataset tenants are non-billable by design.
                continue
    return {"closed_cycles": closed}


@router.post("/api/webhooks/{provider}", response_model=WebhookAckResponse, status_code=status.HTTP_202_ACCEPTED)
async def webhook_ingestion(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    x_webhook_id: str | None = Header(default=None, alias="X-Webhook-Id"),
    db: Session = Depends(get_db),
) -> WebhookAckResponse:
    raw = await request.body()
    if not x_webhook_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")
    expected_signature = hmac.new(
        f"{settings.api_key_secret}:{provider}".encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, x_webhook_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid webhook JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payload must be a JSON object")

    event_id = x_webhook_id or payload.get("id")
    if not event_id:
        event_id = hashlib.sha256(raw).hexdigest()

    ingestion = IngestionService(db)
    event = ingestion.receive_webhook_event(
        provider=provider,
        event_id=str(event_id),
        payload=payload,
        signature=x_webhook_signature,
        user_id=int(payload.get("user_id", 0) or 0) or None,
    )
    if event.status == WebhookProcessStatus.RECEIVED:
        background_tasks.add_task(_process_webhook_event, event.id)

    return WebhookAckResponse(event_id=event.event_id, status=event.status.value)


def _process_webhook_event(event_id: int) -> None:
    from backend.app.database import SessionLocal
    from backend.app.models import WebhookEvent

    db = SessionLocal()
    try:
        event = db.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id))
        if not event:
            return
        IngestionService(db).process_webhook_event(event)
    finally:
        db.close()


@router.post("/api/payments/razorpay/order", response_model=RazorpayOrderResponse)
async def create_razorpay_order(
    payload: RazorpayOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RazorpayOrderResponse:
    service = PaymentService(db)
    result = await service.create_razorpay_order(
        user=current_user,
        amount=payload.amount,
        currency=payload.currency,
        receipt=payload.receipt,
        invoice_number=payload.invoice_number,
    )
    return RazorpayOrderResponse(
        order_id=str(result.get("id")),
        amount=Decimal(result.get("amount", 0)) / Decimal("100"),
        currency=str(result.get("currency", payload.currency)),
        receipt=str(result.get("receipt", payload.receipt)),
    )


@router.post("/api/payments/razorpay/webhook", response_model=RazorpayWebhookResponse)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
) -> RazorpayWebhookResponse:
    body = await request.body()
    service = PaymentService(db)
    if not service.verify_webhook_signature(body, x_razorpay_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    payload = json.loads(body.decode("utf-8"))
    event_type = payload.get("event", "unknown")
    payment = service.process_razorpay_webhook(event_type=event_type, payload=payload)
    return RazorpayWebhookResponse(processed=True, event_type=event_type, payment_status=payment.status)


@router.post("/v1/data", response_model=DataRecordResponse, status_code=status.HTTP_201_CREATED)
def create_data_record(
    payload: DataCreateRequest,
    principal: APIPrincipal = Depends(get_api_principal),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
) -> DataRecordResponse:
    ingestion = IngestionService(db)
    record = ingestion.ingest_user_payload(
        user=principal.user,
        api_key=principal.api_key,
        payload=payload.payload,
        schema_version=payload.schema_version,
        external_id=payload.external_id,
        idempotency_key=payload.idempotency_key or x_idempotency_key,
        method=IngestionMethod.USER_REST,
    )
    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/data",
        method="POST",
        data_volume_bytes=len(json.dumps(payload.payload)),
        compute_units=1,
        idempotency_key=x_idempotency_key,
    )
    return DataRecordResponse(
        id=record.id,
        user_id=record.user_id,
        ingestion_method=record.ingestion_method,
        schema_version=record.schema_version,
        external_id=record.external_id,
        lineage_ref=record.lineage_ref,
        normalized_payload=record.normalized_payload,
        created_at=record.created_at,
    )


@router.post("/v1/data/upload", response_model=FileIngestionResponse)
async def upload_data_file(
    file: UploadFile = File(...),
    principal: APIPrincipal = Depends(get_api_principal),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
) -> FileIngestionResponse:
    content = await file.read()
    records, errors = IngestionService(db).ingest_file_payload(
        user=principal.user,
        api_key=principal.api_key,
        filename=file.filename or "upload.json",
        content=content,
    )
    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/data/upload",
        method="POST",
        data_volume_bytes=len(content),
        compute_units=max(1, len(records)),
        idempotency_key=x_idempotency_key,
    )
    return FileIngestionResponse(
        ingested_count=len(records),
        failed_count=len(errors),
        errors=errors,
    )


@router.get("/v1/data", response_model=DataListResponse)
def list_data_records(
    response: Response,
    principal: APIPrincipal = Depends(get_api_principal),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ingestion_method: IngestionMethod | None = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(created_at|id)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DataListResponse:
    query = select(IngestedRecord).where(IngestedRecord.user_id == principal.user.id)
    if ingestion_method:
        query = query.where(IngestedRecord.ingestion_method == ingestion_method)

    ordering_col = IngestedRecord.created_at if sort_by == "created_at" else IngestedRecord.id
    query = query.order_by(desc(ordering_col) if sort_order == "desc" else asc(ordering_col))

    total_query = select(func.count(IngestedRecord.id)).where(IngestedRecord.user_id == principal.user.id)
    if ingestion_method:
        total_query = total_query.where(IngestedRecord.ingestion_method == ingestion_method)
    total = db.scalar(total_query)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    selected_fields = set(field.strip() for field in fields.split(",") if field.strip()) if fields else set()
    items: list[DataRecordResponse] = []
    for row in rows:
        normalized_payload = row.normalized_payload
        if selected_fields:
            attrs = normalized_payload.get("attributes", {})
            if isinstance(attrs, dict):
                normalized_payload = {
                    **normalized_payload,
                    "attributes": {k: v for k, v in attrs.items() if k in selected_fields},
                }
        items.append(
            DataRecordResponse(
                id=row.id,
                user_id=row.user_id,
                ingestion_method=row.ingestion_method,
                schema_version=row.schema_version,
                external_id=row.external_id,
                lineage_ref=row.lineage_ref,
                normalized_payload=normalized_payload,
                created_at=row.created_at,
            )
        )

    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/data",
        method="GET",
        data_volume_bytes=0,
        compute_units=1,
    )
    response.headers["Cache-Control"] = "public, max-age=30"
    response.headers["Vary"] = "X-API-Key"
    return DataListResponse(items=items, page=page, page_size=page_size, total=int(total or 0))


@router.get("/v1/data/{record_id}", response_model=DataRecordResponse)
def get_data_record(
    record_id: int,
    response: Response,
    principal: APIPrincipal = Depends(get_api_principal),
    db: Session = Depends(get_db),
) -> DataRecordResponse:
    row = db.scalar(select(IngestedRecord).where(IngestedRecord.id == record_id, IngestedRecord.user_id == principal.user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data record not found")

    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/data/{id}",
        method="GET",
        data_volume_bytes=0,
        compute_units=1,
    )
    response.headers["Cache-Control"] = "public, max-age=30"
    response.headers["Vary"] = "X-API-Key"
    return DataRecordResponse(
        id=row.id,
        user_id=row.user_id,
        ingestion_method=row.ingestion_method,
        schema_version=row.schema_version,
        external_id=row.external_id,
        lineage_ref=row.lineage_ref,
        normalized_payload=row.normalized_payload,
        created_at=row.created_at,
    )


@router.get("/v1/usage", response_model=UsageSummaryResponse)
def get_usage_summary(
    principal: APIPrincipal = Depends(get_api_principal),
    db: Session = Depends(get_db),
) -> UsageSummaryResponse:
    billing = BillingService(db)
    cycle = billing.ensure_open_cycle(account=principal.account, plan=principal.plan)
    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/usage",
        method="GET",
        data_volume_bytes=0,
        compute_units=1,
    )
    return UsageSummaryResponse(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        cycle_start=cycle.starts_at,
        cycle_end=cycle.ends_at,
        request_count=int(cycle.request_count or 0),
        data_volume_bytes=0,
        compute_units=0,
    )


@router.get("/v1/billing", response_model=BillingResponse)
def get_billing(
    principal: APIPrincipal = Depends(get_api_principal),
    db: Session = Depends(get_db),
) -> BillingResponse:
    billing = BillingService(db)
    UsageService(db).track_request(
        user_id=principal.user.id,
        api_key_id=principal.api_key.id,
        endpoint="/v1/billing",
        method="GET",
        data_volume_bytes=0,
        compute_units=1,
    )
    return billing.billing_with_invoices(user=principal.user, account=principal.account, plan=principal.plan)
