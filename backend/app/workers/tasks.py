from datetime import UTC, datetime
import logging
from pathlib import Path

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import BillingCycleStatus, IngestionJob, Plan, User, UserAccount
from backend.app.services.billing_service import BillingService
from backend.app.services.ingestion_service import IngestionService
from backend.app.services.usage_service import UsageService
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.app.workers.tasks.flush_usage_counters")
def flush_usage_counters() -> dict[str, int]:
    with SessionLocal() as db:
        try:
            flushed = UsageService(db).flush_redis_aggregates()
            db.commit()
            return {"flushed": flushed}
        except Exception:
            db.rollback()
            logger.exception("Failed to flush usage counters")
            raise


@celery_app.task(name="backend.app.workers.tasks.close_billing_cycles")
def close_billing_cycles() -> dict[str, int]:
    with SessionLocal() as db:
        try:
            now = datetime.now(UTC)
            closed = 0
            rows = db.execute(select(UserAccount, Plan).join(Plan, Plan.id == UserAccount.plan_id)).all()
            for account, plan in rows:
                billing = BillingService(db)
                cycle = billing.ensure_open_cycle(account=account, plan=plan)
                if cycle.status == BillingCycleStatus.OPEN and cycle.ends_at <= now:
                    try:
                        billing.close_cycle_and_generate_invoice(account=account, plan=plan)
                        closed += 1
                    except ValueError:
                        continue
            db.commit()
            return {"closed_cycles": closed}
        except Exception:
            db.rollback()
            logger.exception("Failed to close billing cycles")
            raise


@celery_app.task(name="backend.app.workers.tasks.process_ingestion_upload_job")
def process_ingestion_upload_job(job_id: int, file_path: str) -> dict[str, int | str]:
    with SessionLocal() as db:
        try:
            job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id))
            if not job:
                logger.error("Ingestion job not found for job_id=%s", job_id)
                db.commit()
                return {"job_id": job_id, "status": "NOT_FOUND"}

            user = db.scalar(select(User).where(User.id == job.user_id))
            if not user:
                job.status = "FAILED"
                job.error_message = "User not found"
                db.commit()
                return {"job_id": job_id, "status": "FAILED"}

            path = Path(file_path)
            if not path.exists():
                job.status = "FAILED"
                job.error_message = "Uploaded file not found"
                db.commit()
                return {"job_id": job_id, "status": "FAILED"}

            job.status = "PROCESSING"
            db.commit()

            content = path.read_bytes()
            service = IngestionService(db)
            metadata = {
                "tenant_id": f"tenant-{user.id}",
                "uploaded_by": job.uploaded_by,
                "data_origin": job.data_origin,
                "is_billable": bool(job.is_billable),
                "dataset_id": job.id,
            }
            records, errors = service.ingest_file_payload(
                user=user,
                api_key=None,
                filename=job.file_name or path.name,
                content=content,
                metadata=metadata,
            )

            job.record_count = len(records)
            if len(records) == 0:
                job.status = "FAILED"
                job.error_message = "; ".join(errors[:5]) if errors else "No valid records ingested"
            else:
                job.status = "READY"
                job.error_message = "; ".join(errors[:5]) if errors else None
            db.commit()

            return {
                "job_id": job_id,
                "status": job.status,
                "ingested_count": len(records),
                "failed_count": len(errors),
            }
        except Exception as exc:
            db.rollback()
            logger.exception("Ingestion job processing failed for job_id=%s", job_id)
            job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id))
            if job:
                job.status = "FAILED"
                job.error_message = str(exc)
                db.commit()
            return {"job_id": job_id, "status": "FAILED"}
