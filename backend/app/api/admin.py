from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.deps import require_role
from backend.app.database import get_db
from backend.app.models import CloudProvider, IngestedRecord, User, UserRole
from backend.app.schemas.auth import MessageResponse
from backend.app.schemas.dashboard import AdminMetricsResponse, AdminMigrationResponse, AdminUserResponse
from backend.app.schemas.platform import (
    AdminIngestedRecordResponse,
    AdminIngestedRecordUpdateRequest,
    AdminUserDetailResponse,
    BillingExportIngestRequest,
    BillingExportIngestResponse,
)
from backend.app.services.admin_service import AdminService
from backend.app.services.billing_export_ingestion_service import BillingExportIngestionService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin_user_guard(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> list[AdminUserResponse]:
    service = AdminService(db)
    return service.get_users()


@router.get("/metrics", response_model=AdminMetricsResponse)
def admin_metrics(
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> AdminMetricsResponse:
    service = AdminService(db)
    from backend.app.main import get_uptime_seconds

    return service.get_admin_metrics(api_uptime_seconds=get_uptime_seconds())


@router.get("/migrations", response_model=list[AdminMigrationResponse])
def admin_migrations(
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> list[AdminMigrationResponse]:
    service = AdminService(db)
    return service.get_migrations()


@router.post("/billing/ingest", response_model=BillingExportIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def admin_ingest_billing_export(
    payload: BillingExportIngestRequest,
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> BillingExportIngestResponse:
    target_user = db.get(User, payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")

    service = BillingExportIngestionService(db)
    try:
        run = service.ingest_rows(
            user_id=payload.user_id,
            provider=CloudProvider(payload.provider),
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            rows=payload.rows,
            idempotency_key=payload.idempotency_key,
            window_start=payload.window_start,
            window_end=payload.window_end,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BillingExportIngestResponse(
        run_id=run.id,
        provider=run.provider.value,
        source_type=run.source_type,
        status=run.status,
        source_ref=run.source_ref,
        idempotency_key=run.idempotency_key,
        records_seen=run.records_seen,
        records_inserted=run.records_inserted,
        skipped_non_storage=run.skipped_non_storage,
        window_start=run.window_start,
        window_end=run.window_end,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/users/{user_id}/detail", response_model=AdminUserDetailResponse)
def admin_user_detail(
    user_id: int,
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    service = AdminService(db)
    try:
        return service.get_user_detail(user_id=user_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _to_admin_record_response(record: IngestedRecord) -> AdminIngestedRecordResponse:
    return AdminIngestedRecordResponse(
        id=record.id,
        user_id=record.user_id,
        data_source_id=record.data_source_id,
        ingestion_method=record.ingestion_method,
        schema_version=record.schema_version,
        external_id=record.external_id,
        lineage_ref=record.lineage_ref,
        raw_payload=record.raw_payload,
        normalized_payload=record.normalized_payload,
        created_at=record.created_at,
        processed_at=record.processed_at,
    )


@router.get("/records", response_model=list[AdminIngestedRecordResponse])
def admin_records(
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> list[AdminIngestedRecordResponse]:
    service = AdminService(db)
    rows = service.list_ingested_records(user_id=user_id, limit=max(1, min(limit, 500)), offset=max(0, offset))
    return [_to_admin_record_response(row) for row in rows]


@router.patch("/records/{record_id}", response_model=AdminIngestedRecordResponse)
def admin_update_record(
    record_id: int,
    payload: AdminIngestedRecordUpdateRequest,
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> AdminIngestedRecordResponse:
    service = AdminService(db)
    try:
        row = service.update_ingested_record(
            record_id=record_id,
            external_id=payload.external_id,
            schema_version=payload.schema_version,
            raw_payload=payload.raw_payload,
            normalized_payload=payload.normalized_payload,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingested record not found")
    return _to_admin_record_response(row)


@router.delete("/records/{record_id}", response_model=MessageResponse)
def admin_delete_record(
    record_id: int,
    _: User = Depends(_admin_user_guard),
    db: Session = Depends(get_db),
) -> MessageResponse:
    service = AdminService(db)
    try:
        service.delete_ingested_record(record_id=record_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingested record not found")
    return MessageResponse(message="Record deleted")
