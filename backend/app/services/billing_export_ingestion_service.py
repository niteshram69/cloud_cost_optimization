from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import BillingIngestionRun, BillingUsageRecord, CloudProvider, DataTemperature
from backend.app.services.bucket_aggregation_service import BucketAggregationService


class BillingExportIngestionService:
    SUPPORTED_SOURCES = {
        "AWS_CUR": CloudProvider.AWS,
        "GCP_BQ_EXPORT": CloudProvider.GCP,
    }

    def __init__(self, db: Session):
        self.db = db

    def ingest_rows(
        self,
        *,
        user_id: int,
        provider: CloudProvider,
        source_type: str,
        source_ref: str,
        rows: list[dict[str, Any]],
        idempotency_key: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        dry_run: bool = False,
    ) -> BillingIngestionRun:
        expected_provider = self.SUPPORTED_SOURCES.get(source_type.upper())
        if expected_provider is None:
            raise ValueError(f"Unsupported source_type '{source_type}'. Use AWS_CUR or GCP_BQ_EXPORT.")
        if expected_provider != provider:
            raise ValueError("source_type and provider mismatch")

        run_key = idempotency_key or self._derive_idempotency_key(
            user_id=user_id,
            provider=provider,
            source_type=source_type.upper(),
            source_ref=source_ref,
            rows_count=len(rows),
            window_start=window_start,
            window_end=window_end,
        )
        existing = self.db.scalar(
            select(BillingIngestionRun).where(
                BillingIngestionRun.user_id == user_id,
                BillingIngestionRun.provider == provider,
                BillingIngestionRun.source_type == source_type.upper(),
                BillingIngestionRun.idempotency_key == run_key,
            )
        )
        if existing and existing.status in {"COMPLETED", "DRY_RUN"}:
            return existing

        run = existing or BillingIngestionRun(
            user_id=user_id,
            provider=provider,
            source_type=source_type.upper(),
            source_ref=source_ref.strip() or "manual-import",
            idempotency_key=run_key,
            status="RUNNING",
            window_start=window_start,
            window_end=window_end,
            started_at=datetime.now(UTC),
        )
        if existing is None:
            self.db.add(run)
            self.db.flush()

        records_seen = 0
        records_inserted = 0
        skipped_non_storage = 0

        try:
            for row in rows:
                if not isinstance(row, dict):
                    skipped_non_storage += 1
                    continue
                records_seen += 1
                normalized_row = self._normalize_row_keys(row)
                normalized = self._normalize_row(
                    provider=provider,
                    source_type=source_type.upper(),
                    row=normalized_row,
                    window_start=window_start,
                    window_end=window_end,
                )
                if normalized is None:
                    skipped_non_storage += 1
                    continue

                source_hash = self._source_record_hash(provider=provider, normalized=normalized)
                duplicate = self.db.scalar(
                    select(BillingUsageRecord.id).where(
                        BillingUsageRecord.user_id == user_id,
                        BillingUsageRecord.provider == provider,
                        BillingUsageRecord.source_record_hash == source_hash,
                    )
                )
                if duplicate:
                    continue

                if not dry_run:
                    self.db.add(
                        BillingUsageRecord(
                            user_id=user_id,
                            ingestion_run_id=run.id,
                            provider=provider,
                            source_type=source_type.upper(),
                            billing_account_id=normalized.get("billing_account_id"),
                            project_id=normalized.get("project_id"),
                            bucket_id=normalized.get("bucket_id"),
                            region=normalized["region"],
                            storage_class=normalized["storage_class"],
                            canonical_tier=normalized["canonical_tier"],
                            sku_id=normalized.get("sku_id"),
                            sku_description=normalized["sku_description"],
                            usage_start=normalized["usage_start"],
                            usage_end=normalized["usage_end"],
                            usage_quantity=normalized["usage_quantity"],
                            usage_unit=normalized["usage_unit"],
                            cost_usd=normalized["cost_usd"],
                            currency=normalized["currency"],
                            pricing_version=normalized.get("pricing_version"),
                            source_record_hash=source_hash,
                            source_payload=row,
                        )
                    )
                records_inserted += 1

            run.records_seen = int(records_seen)
            run.records_inserted = int(records_inserted)
            run.skipped_non_storage = int(skipped_non_storage)
            run.status = "DRY_RUN" if dry_run else "COMPLETED"
            run.completed_at = datetime.now(UTC)
            run.error_message = None
            self.db.commit()

            if not dry_run and records_inserted > 0:
                BucketAggregationService(self.db).apply_billing_overrides_for_user(
                    user_id=user_id,
                    provider=provider,
                    lookback_days=45,
                )
                self.db.commit()

            self.db.refresh(run)
            return run
        except Exception as exc:
            self.db.rollback()
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return run

    def _normalize_row(
        self,
        *,
        provider: CloudProvider,
        source_type: str,
        row: dict[str, Any],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> dict[str, Any] | None:
        if provider == CloudProvider.AWS and source_type == "AWS_CUR":
            return self._normalize_aws_cur_row(row=row, window_start=window_start, window_end=window_end)
        if provider == CloudProvider.GCP and source_type == "GCP_BQ_EXPORT":
            return self._normalize_gcp_bq_row(row=row, window_start=window_start, window_end=window_end)
        return None

    @staticmethod
    def _normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        for key, value in row.items():
            if not isinstance(key, str):
                continue
            normalized_key = key.lower().replace(".", "_")
            if normalized_key not in normalized:
                normalized[normalized_key] = value
        return normalized

    def _normalize_aws_cur_row(
        self,
        *,
        row: dict[str, Any],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> dict[str, Any] | None:
        product_code = self._as_str(
            row.get("line_item_product_code")
            or row.get("product_product_name")
            or row.get("product_servicecode")
            or row.get("service")
        )
        usage_type = self._as_str(row.get("line_item_usage_type") or row.get("product_usagetype"))
        operation = self._as_str(row.get("line_item_operation") or row.get("operation"))
        sku_desc = self._as_str(row.get("line_item_line_item_description") or row.get("line_item_description"))
        scope_text = " ".join([product_code, usage_type, operation, sku_desc]).lower()

        if "s3" not in scope_text and "storage" not in scope_text:
            return None
        if "request" in scope_text and "retrieval" not in scope_text and "storage" not in scope_text:
            return None
        if not any(token in scope_text for token in ("storage", "timedstorage", "archive", "glacier", "ia", "standard", "retrieval", "byte")):
            return None

        usage_start = self._parse_dt(
            row.get("line_item_usage_start_date") or row.get("usage_start_time"),
            fallback=window_start,
        )
        usage_end = self._parse_dt(
            row.get("line_item_usage_end_date") or row.get("usage_end_time"),
            fallback=window_end or usage_start,
        )
        usage_quantity = self._to_float(row.get("line_item_usage_amount") or row.get("usage_quantity") or 0.0)
        cost = self._to_float(row.get("line_item_unblended_cost") or row.get("line_item_blended_cost") or row.get("cost") or 0.0)
        currency = self._as_str(row.get("line_item_currency_code") or row.get("currency") or "USD").upper()
        if cost < 0:
            return None
        if currency not in {"USD", "US$"}:
            return None

        storage_class = self._normalize_storage_class(
            self._as_str(row.get("product_storage_class") or row.get("storage_class") or usage_type)
        )
        canonical_tier = self._canonical_tier_from_text(" ".join([storage_class, usage_type, sku_desc]))
        bucket_id = self._extract_bucket_id(
            row.get("bucket_id")
            or row.get("resource_id")
            or row.get("line_item_resource_id")
            or self._nested(row, "resource_tags", "bucket")
            or self._nested(row, "resource_tags", "aws:bucketName")
        )
        region = self._normalize_region(
            self._as_str(
                row.get("product_region")
                or row.get("product_location")
                or row.get("region")
                or row.get("line_item_availability_zone")
                or "global"
            )
        )

        return {
            "billing_account_id": self._as_str(row.get("bill_payer_account_id") or row.get("payer_account_id")) or None,
            "project_id": self._as_str(row.get("line_item_usage_account_id") or row.get("linked_account_id")) or None,
            "bucket_id": bucket_id,
            "region": region,
            "storage_class": storage_class,
            "canonical_tier": canonical_tier,
            "sku_id": self._as_str(row.get("line_item_usage_type") or row.get("sku_id")) or None,
            "sku_description": sku_desc or usage_type or "AWS CUR storage line item",
            "usage_start": usage_start,
            "usage_end": usage_end,
            "usage_quantity": max(usage_quantity, 0.0),
            "usage_unit": self._as_str(row.get("pricing_unit") or row.get("line_item_usage_unit") or "GB-Mo"),
            "cost_usd": max(cost, 0.0),
            "currency": "USD",
            "pricing_version": usage_start.date().isoformat(),
        }

    def _normalize_gcp_bq_row(
        self,
        *,
        row: dict[str, Any],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> dict[str, Any] | None:
        service_description = self._as_str(
            self._nested(row, "service", "description")
            or row.get("service_description")
            or row.get("service")
        )
        sku_description = self._as_str(
            self._nested(row, "sku", "description")
            or row.get("sku_description")
            or row.get("description")
        )
        scope_text = " ".join([service_description, sku_description]).lower()
        if "storage" not in scope_text:
            return None
        if "class a" in scope_text or "class b" in scope_text:
            return None

        usage_start = self._parse_dt(
            row.get("usage_start_time") or row.get("usage_start"),
            fallback=window_start,
        )
        usage_end = self._parse_dt(
            row.get("usage_end_time") or row.get("usage_end"),
            fallback=window_end or usage_start,
        )
        usage_quantity = self._to_float(
            self._nested(row, "usage", "amount")
            or row.get("usage_amount")
            or row.get("usage_quantity")
            or 0.0
        )
        usage_unit = self._as_str(
            self._nested(row, "usage", "unit")
            or row.get("usage_unit")
            or "GiBy.mo"
        )
        cost = self._to_float(row.get("cost") or row.get("cost_usd") or 0.0)
        currency = self._as_str(row.get("currency") or "USD").upper()
        if cost < 0:
            return None
        if currency not in {"USD", "US$"}:
            return None

        storage_class = self._normalize_storage_class(
            self._as_str(
                row.get("storage_class")
                or self._nested(row, "labels", "storage_class")
                or sku_description
            )
        )
        canonical_tier = self._canonical_tier_from_text(" ".join([storage_class, sku_description]))
        bucket_id = self._extract_bucket_id(
            row.get("bucket_id")
            or self._nested(row, "labels", "bucket_name")
            or self._nested(row, "resource", "name")
            or row.get("resource_name")
        )
        region = self._normalize_region(
            self._as_str(
                self._nested(row, "location", "region")
                or self._nested(row, "location", "location")
                or row.get("region")
                or "global"
            )
        )

        return {
            "billing_account_id": self._as_str(row.get("billing_account_id")) or None,
            "project_id": self._as_str(
                self._nested(row, "project", "id")
                or row.get("project_id")
            )
            or None,
            "bucket_id": bucket_id,
            "region": region,
            "storage_class": storage_class,
            "canonical_tier": canonical_tier,
            "sku_id": self._as_str(self._nested(row, "sku", "id") or row.get("sku_id")) or None,
            "sku_description": sku_description or "GCP billing export storage line item",
            "usage_start": usage_start,
            "usage_end": usage_end,
            "usage_quantity": max(usage_quantity, 0.0),
            "usage_unit": usage_unit,
            "cost_usd": max(cost, 0.0),
            "currency": "USD",
            "pricing_version": usage_start.date().isoformat(),
        }

    def _canonical_tier_from_text(self, text: str) -> DataTemperature:
        value = str(text or "").lower()
        if any(token in value for token in ("archive", "glacier", "deep archive")):
            return DataTemperature.ARCHIVE
        if any(token in value for token in ("coldline", "nearline", "standard-ia", "one zone-ia", "infrequent", "cool")):
            return DataTemperature.COLD
        return DataTemperature.HOT

    def _normalize_storage_class(self, storage_class: str) -> str:
        text = self._as_str(storage_class).upper()
        if not text:
            return "STANDARD"
        if "DEEP" in text and "ARCHIVE" in text:
            return "DEEP_ARCHIVE"
        if "ARCHIVE" in text or "GLACIER" in text:
            return "ARCHIVE"
        if "COLDLINE" in text:
            return "COLDLINE"
        if "NEARLINE" in text:
            return "NEARLINE"
        if "STANDARD-IA" in text or "STANDARD IA" in text or "INFREQUENT" in text or "ONE ZONE-IA" in text:
            return "STANDARD_IA"
        return "STANDARD"

    def _extract_bucket_id(self, raw: Any) -> str | None:
        text = self._as_str(raw)
        if not text:
            return None
        if text.startswith("arn:aws:s3:::"):
            stripped = text.replace("arn:aws:s3:::", "", 1)
            return stripped.split("/", 1)[0].strip() or None
        if "/buckets/" in text:
            return text.split("/buckets/", 1)[1].split("/", 1)[0].strip() or None
        if "/" in text:
            head = text.split("/", 1)[0].strip()
            if head and not head.startswith("projects/"):
                return head
        return text

    def _normalize_region(self, region: str) -> str:
        value = self._as_str(region).lower()
        if not value:
            return "global"
        return value.replace(" ", "-")

    def _source_record_hash(self, *, provider: CloudProvider, normalized: dict[str, Any]) -> str:
        payload = {
            "provider": provider.value,
            "bucket_id": normalized.get("bucket_id"),
            "region": normalized.get("region"),
            "storage_class": normalized.get("storage_class"),
            "sku_id": normalized.get("sku_id"),
            "usage_start": normalized["usage_start"].isoformat(),
            "usage_end": normalized["usage_end"].isoformat(),
            "usage_quantity": normalized["usage_quantity"],
            "cost_usd": normalized["cost_usd"],
            "currency": normalized["currency"],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _derive_idempotency_key(
        self,
        *,
        user_id: int,
        provider: CloudProvider,
        source_type: str,
        source_ref: str,
        rows_count: int,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> str:
        payload = {
            "user_id": user_id,
            "provider": provider.value,
            "source_type": source_type,
            "source_ref": source_ref,
            "rows_count": rows_count,
            "window_start": window_start.isoformat() if window_start else None,
            "window_end": window_end.isoformat() if window_end else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _parse_dt(self, raw: Any, *, fallback: datetime | None) -> datetime:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
        text = self._as_str(raw)
        if text:
            normalized = text.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
        if fallback is not None:
            return fallback if fallback.tzinfo is not None else fallback.replace(tzinfo=UTC)
        return datetime.now(UTC)

    def _nested(self, payload: dict[str, Any], *path: str) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _to_float(self, raw: Any) -> float:
        try:
            return float(raw)
        except Exception:
            return 0.0

    def _as_str(self, raw: Any) -> str:
        if raw is None:
            return ""
        return str(raw).strip()
