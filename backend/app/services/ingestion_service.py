import asyncio
import csv
import hashlib
import io
import json
import logging
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import (
    APIKey,
    CloudProvider,
    DataSource,
    DataSourceType,
    DataTemperature,
    IngestedRecord,
    IngestionMethod,
    Recommendation,
    RecommendationStatus,
    StorageRecord,
    User,
    WebhookEvent,
    WebhookProcessStatus,
)
from backend.app.services.bucket_aggregation_service import BucketAggregationInput, BucketAggregationService
from backend.app.services.metadata_classifier_service import MetadataFeatures, get_metadata_classifier

logger = logging.getLogger(__name__)


class IngestionService:
    BASE_STORAGE_RATES: dict[str, float] = {
        "STANDARD": 0.023,
        "STANDARD-IA": 0.0125,
        "COOL BLOB": 0.0028,
        "ARCHIVE": 0.00099,
    }
    OFFICIAL_API_MAX_ATTEMPTS = 5
    TEMPERATURE_RAW_MAX = 3.0
    ARCHIVE_REQUESTS_THRESHOLD = 200
    LARGE_OBJECT_TB = 5.0
    RETRIEVAL_PENALTY_HIGH = 200.0

    def __init__(self, db: Session):
        self.db = db

    def validate_file_schema(self, *, filename: str, content: bytes) -> list[str]:
        filename_lower = filename.lower()
        text = content.decode("utf-8", errors="ignore")

        if filename_lower.endswith(".json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return ["Invalid JSON payload"]
            if isinstance(payload, dict):
                return [] if payload else ["JSON object cannot be empty"]
            if isinstance(payload, list):
                if not payload:
                    return ["JSON array cannot be empty"]
                if any(not isinstance(item, dict) for item in payload):
                    return ["JSON array must contain only objects"]
                return []
            return ["JSON upload must be an object or array of objects"]

        if filename_lower.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                return ["CSV must include a header row"]
            if not any(name and name.strip() for name in reader.fieldnames):
                return ["CSV header contains empty column names"]
            return []

        return ["Unsupported file type. Only CSV or JSON is allowed"]

    def ingest_user_payload(
        self,
        *,
        user: User,
        api_key: APIKey | None,
        payload: dict[str, Any],
        schema_version: str,
        external_id: str | None,
        idempotency_key: str | None,
        method: IngestionMethod = IngestionMethod.USER_REST,
    ) -> IngestedRecord:
        normalized = self._normalize_payload(payload=payload, schema_version=schema_version)
        record = IngestedRecord(
            user_id=user.id,
            api_key_id=api_key.id if api_key else None,
            ingestion_method=method,
            schema_version=schema_version,
            external_id=external_id,
            idempotency_key=idempotency_key,
            lineage_ref=f"user:{user.id}:{method.value}",
            content_hash=self._content_hash(payload),
            raw_payload=payload,
            normalized_payload=normalized,
            is_processed=True,
            processed_at=datetime.now(UTC),
        )
        self.db.add(record)
        try:
            self.db.flush()
            self._project_dashboard_entities(user=user, record=record, payload=payload)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Duplicate idempotency key for this ingestion method") from exc
        except ValueError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception("Ingestion transaction failed for record %s", record.id)
            raise ValueError("Ingestion failed due to invalid required metadata features.") from exc
        self.db.refresh(record)
        return record

    def ingest_file_payload(
        self,
        *,
        user: User,
        api_key: APIKey | None,
        filename: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[list[IngestedRecord], list[str]]:
        errors: list[str] = []
        records: list[IngestedRecord] = []
        text = content.decode("utf-8", errors="ignore")
        filename_lower = filename.lower()

        if filename_lower.endswith(".json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                return [], [f"Invalid JSON file: {exc}"]
            if isinstance(payload, dict):
                payload = [payload]
            if not isinstance(payload, list):
                return [], ["JSON upload must be an object or array of objects"]

            for index, row in enumerate(payload):
                if not isinstance(row, dict):
                    errors.append(f"Row {index} is not an object")
                    continue
                try:
                    records.append(
                        self.ingest_user_payload(
                            user=user,
                            api_key=api_key,
                            payload=self._with_metadata(row, metadata),
                            schema_version="v1",
                            external_id=str(row.get("id", "")) or None,
                            idempotency_key=row.get("idempotency_key"),
                            method=IngestionMethod.USER_FILE_UPLOAD,
                        )
                    )
                except ValueError as exc:
                    errors.append(f"Row {index}: {exc}")
            return records, errors

        if filename_lower.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text))
            for index, row in enumerate(reader):
                normalized_row = dict(row)
                try:
                    records.append(
                        self.ingest_user_payload(
                            user=user,
                            api_key=api_key,
                            payload=self._with_metadata(normalized_row, metadata),
                            schema_version="v1",
                            external_id=str(normalized_row.get("id", "")) or None,
                            idempotency_key=normalized_row.get("idempotency_key"),
                            method=IngestionMethod.USER_FILE_UPLOAD,
                        )
                    )
                except ValueError as exc:
                    errors.append(f"Row {index}: {exc}")
            return records, errors

        return [], ["Unsupported file type. Only CSV or JSON is allowed"]

    def _with_metadata(self, payload: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not metadata:
            return payload
        return {
            "metadata": metadata,
            "record": payload,
        }

    def _project_dashboard_entities(
        self,
        *,
        user: User,
        record: IngestedRecord,
        payload: dict[str, Any],
    ) -> None:
        row, metadata = self._extract_row_and_metadata(payload)
        data_origin = str(metadata.get("data_origin", "")).upper()
        if data_origin == "PUBLIC_DATASET":
            return
        dataset_id = self._to_int(metadata.get("dataset_id") or metadata.get("ingestion_job_id"))

        resource_name = (
            self._as_str(row.get("resource_name"))
            or self._as_str(row.get("resource_id"))
            or self._as_str(row.get("file_name"))
            or self._as_str(row.get("file_id"))
            or self._as_str(row.get("object_key"))
            or self._as_str(row.get("object_name"))
            or self._as_str(row.get("id"))
            or self._as_str(row.get("name"))
            or self._as_str(record.external_id)
            or f"record-{record.id}"
        )

        provider = self._map_provider(
            row.get("provider")
            or row.get("cloud_provider")
            or row.get("cloud")
            or row.get("cloud_name")
            or self._nested(payload, "provider")
            or "MULTI"
        )
        region = (
            self._as_str(row.get("region"))
            or self._as_str(row.get("location"))
            or self._as_str(row.get("region_name"))
            or self._as_str(row.get("availability_zone"))
            or "global"
        )

        requests_30d = self._required_number(
            row=row,
            payload=payload,
            field_name="requests_30d",
            paths=[
                ("requests_30d",),
                ("access_frequency_30d",),
                ("read_count_30d",),
                ("access_count",),
                ("usage_metrics", "requests_30d"),
                ("usage_metrics", "access_frequency_30d"),
            ],
        )
        latency_ms = self._optional_number(
            row=row,
            payload=payload,
            field_name="latency_ms",
            paths=[
                ("latency_ms",),
                ("avg_latency_ms",),
                ("latency",),
                ("response_time_ms",),
                ("p95_latency_ms",),
                ("performance_metrics", "avg_latency_ms"),
                ("performance_metrics", "latency_ms"),
                ("performance_metrics", "latency"),
                ("performance_metrics", "response_time_ms"),
                ("performance_metrics", "p95_latency_ms"),
                ("metrics", "latency_ms"),
                ("observability", "latency_ms"),
                ("network", "latency_ms"),
            ],
        )
        if latency_ms is None:
            latency_ms = self._fallback_latency_ms(
                row=row,
                payload=payload,
                requests_30d=requests_30d,
            )
        size_mb = self._to_float(
            row.get("size_mb")
            or row.get("object_size_mb")
            or row.get("file_size_mb")
            or row.get("size")
            or row.get("object_size")
            or 0.0
        )
        if size_mb <= 0:
            size_bytes = self._to_float(
                row.get("size_bytes")
                or row.get("object_size_bytes")
                or row.get("file_size_bytes")
                or row.get("bytes")
                or 0.0
            )
            if size_bytes > 0:
                size_mb = size_bytes / (1024.0 * 1024.0)

        storage_class_for_cost = (
            self._as_str(row.get("storage_class"))
            or self._as_str(row.get("storage_tier"))
            or self._as_str(row.get("current_tier"))
            or self._as_str(row.get("tier"))
            or self._as_str(self._nested(payload, "storage_class"))
            or "Standard"
        )
        monthly_cost_feature = self._optional_number(
            row=row,
            payload=payload,
            field_name="monthly_cost",
            paths=[
                ("monthly_cost",),
                ("monthly_storage_cost",),
                ("cost_usd",),
                ("storage_cost_usd",),
                ("cost",),
                ("amount",),
                ("cost_metrics", "monthly_cost_usd"),
                ("cost_metrics", "monthly_cost"),
                ("cost_metrics", "cost"),
            ],
        )
        if monthly_cost_feature is None or monthly_cost_feature <= 0:
            monthly_cost_feature = self._derive_monthly_cost_from_storage_class(
                size_mb=size_mb,
                storage_class=storage_class_for_cost,
            )

        object_count = self._optional_number(
            row=row,
            payload=payload,
            field_name="object_count",
            paths=[
                ("object_count",),
                ("objects_count",),
                ("objects",),
                ("total_objects",),
                ("num_objects",),
                ("file_count",),
                ("total_files",),
                ("storage_metrics", "object_count"),
            ],
            strict_gt=True,
        )
        if object_count is None or object_count <= 0:
            object_count = 1.0
        metadata_features = MetadataFeatures(
            requests_30d=float(requests_30d),
            latency_ms=float(latency_ms),
            monthly_cost=float(monthly_cost_feature),
            object_count=float(object_count),
        )
        ml_classification = get_metadata_classifier().classify(metadata_features)
        last_access_days = self._optional_number(
            row=row,
            payload=payload,
            field_name="last_access_days",
            paths=[
                ("last_access_days",),
                ("last_accessed_days",),
                ("usage_metrics", "last_access_days"),
                ("metrics", "last_access_days"),
            ],
        )
        if last_access_days is None:
            last_access_raw = (
                row.get("last_accessed_at")
                or row.get("last_access_at")
                or row.get("last_accessed")
                or self._nested(payload, "last_accessed_at")
                or self._nested(payload, "last_access_at")
                or self._nested(payload, "last_accessed")
                or self._nested(payload, "usage_metrics", "last_accessed_at")
            )
            if last_access_raw is not None:
                last_access_days = self._days_since(last_access_raw)

        requests_90d = self._optional_number(
            row=row,
            payload=payload,
            field_name="requests_90d",
            paths=[
                ("requests_90d",),
                ("access_frequency_90d",),
                ("usage_metrics", "requests_90d"),
                ("usage_metrics", "access_frequency_90d"),
            ],
        )
        read_write_ratio = self._optional_number(
            row=row,
            payload=payload,
            field_name="read_write_ratio",
            paths=[
                ("read_write_ratio",),
                ("usage_metrics", "read_write_ratio"),
                ("metrics", "read_write_ratio"),
            ],
        )
        access_std_dev = self._optional_number(
            row=row,
            payload=payload,
            field_name="access_std_dev",
            paths=[
                ("access_std_dev",),
                ("access_variance",),
                ("usage_metrics", "access_std_dev"),
            ],
        )
        retrieval_cost_per_gb = self._optional_number(
            row=row,
            payload=payload,
            field_name="retrieval_cost_per_gb",
            paths=[
                ("retrieval_cost_per_gb",),
                ("retrieval_cost",),
                ("retrieval_cost_usd",),
                ("cost_metrics", "retrieval_cost_per_gb"),
                ("cost_metrics", "retrieval_cost"),
            ],
        )
        object_size_bytes = float(size_mb) * 1024.0 * 1024.0 if size_mb > 0 else 0.0

        temperature_tier = self._temperature_tier_from_signals(
            requests_30d=float(requests_30d),
            requests_90d=requests_90d,
            last_access_days=last_access_days,
            read_write_ratio=read_write_ratio,
            access_std_dev=access_std_dev,
            object_size_bytes=object_size_bytes,
            retrieval_cost_per_gb=retrieval_cost_per_gb,
        )
        if temperature_tier is None:
            temperature = ml_classification.selected
        else:
            temperature = self._map_tier_to_temperature(temperature_tier)

        storage_cost = self._to_float(
            row.get("storage_cost")
            or row.get("monthly_cost")
            or row.get("monthly_storage_cost")
            or row.get("cost_usd")
            or row.get("storage_cost_usd")
            or row.get("cost")
            or row.get("amount")
            or self._nested(row, "cost_metrics", "monthly_cost_usd")
            or self._nested(row, "cost_metrics", "monthly_cost")
            or self._nested(row, "cost_metrics", "cost")
            or self._nested(payload, "cost_metrics", "monthly_cost_usd")
            or self._nested(payload, "cost_metrics", "monthly_cost")
            or self._nested(payload, "cost_metrics", "cost")
            or monthly_cost_feature
            or 0.0
        )
        if storage_cost <= 0 and size_mb > 0:
            rate_per_gb = 0.023 if temperature == DataTemperature.HOT else 0.0125 if temperature == DataTemperature.COLD else 0.004
            storage_cost = (size_mb / 1024.0) * rate_per_gb

        estimated_savings = self._to_float(
            row.get("estimated_savings")
            or row.get("estimated_savings_usd")
            or row.get("potential_savings")
            or row.get("savings")
            or row.get("optimization_savings")
            or (
                round(
                    storage_cost
                    * (
                        0.0
                        if temperature == DataTemperature.HOT
                        else 0.32 if temperature == DataTemperature.COLD else 0.58
                    ),
                    4,
                )
                if storage_cost > 0
                else 0.0
            )
        )

        input_confidence = self._to_float(
            row.get("classification_confidence")
            or row.get("confidence")
            or row.get("ml_confidence")
            or self._nested(payload, "ml", "confidence")
            or 0.0
        )
        confidence = input_confidence if input_confidence > 0 else ml_classification.ml_confidence
        confidence = min(0.99, max(0.05, confidence))

        storage = self.db.scalar(
            select(StorageRecord)
            .where(StorageRecord.user_id == user.id, StorageRecord.resource_name == resource_name)
            .order_by(desc(StorageRecord.updated_at), desc(StorageRecord.id))
        )
        if storage:
            storage.provider = provider
            storage.region = region
            storage.storage_cost = float(storage_cost)
            storage.estimated_savings = float(estimated_savings)
            storage.temperature = temperature
            storage.classification_confidence = float(confidence)
        else:
            storage = StorageRecord(
                user_id=user.id,
                resource_name=resource_name,
                provider=provider,
                region=region,
                storage_cost=float(storage_cost),
                estimated_savings=float(estimated_savings),
                temperature=temperature,
                classification_confidence=float(confidence),
            )
            self.db.add(storage)
        self.db.flush()

        bucket_service = BucketAggregationService(self.db)
        bucket_id = self._resolve_bucket_id(
            row=row,
            payload=payload,
            metadata=metadata,
            provider=provider,
            resource_name=resource_name,
        )
        bucket_aggregate = bucket_service.upsert_object_observation(
            BucketAggregationInput(
                user_id=user.id,
                bucket_id=bucket_id,
                cloud_provider=provider,
                region=region,
                storage_class=storage_class_for_cost,
                resource_name=resource_name,
                size_gb=max(size_mb / 1024.0, 0.0),
                requests_30d=float(requests_30d),
                estimated_monthly_cost_usd=float(storage_cost),
                latency_ms=float(latency_ms),
                storage_record_id=storage.id,
            )
        )

        current_tier = (
            self._as_str(row.get("current_tier"))
            or self._as_str(row.get("storage_tier"))
            or self._as_str(row.get("storage_class"))
            or "STANDARD"
        )
        recommendation_resource_name = bucket_aggregate.bucket_id
        recommendation_temperature = bucket_aggregate.temperature
        recommended_tier = self._as_str(row.get("recommended_tier")) or self._as_str(row.get("recommended_storage_class"))
        if not recommended_tier:
            if recommendation_temperature == DataTemperature.ARCHIVE:
                recommended_tier = "ARCHIVE"
            elif recommendation_temperature == DataTemperature.COLD:
                recommended_tier = "INFREQUENT_ACCESS"
            else:
                recommended_tier = "STANDARD"

        base_bucket_cost = (
            float(bucket_aggregate.actual_monthly_cost_usd)
            if bucket_aggregate.has_real_billing and bucket_aggregate.actual_monthly_cost_usd is not None
            else float(bucket_aggregate.estimated_monthly_cost_usd)
        )
        savings_ratio = (
            0.0
            if recommendation_temperature == DataTemperature.HOT
            else 0.32 if recommendation_temperature == DataTemperature.COLD else 0.58
        )
        recommendation_savings = round(max(base_bucket_cost * savings_ratio, 0.0), 4)
        if recommendation_savings <= 0 and estimated_savings > 0:
            recommendation_savings = round(float(estimated_savings), 4)

        if recommendation_savings <= 0:
            return

        priority = "HIGH" if recommendation_savings >= 100 else "MEDIUM" if recommendation_savings >= 20 else "LOW"
        recommendation = self.db.scalar(
            select(Recommendation)
            .where(
                Recommendation.user_id == user.id,
                Recommendation.resource_name == recommendation_resource_name,
                Recommendation.status == RecommendationStatus.OPEN,
                Recommendation.dataset_id == dataset_id,
            )
            .order_by(desc(Recommendation.created_at), desc(Recommendation.id))
        )
        if recommendation:
            recommendation.dataset_id = dataset_id
            recommendation.current_tier = current_tier
            recommendation.recommended_tier = recommended_tier
            recommendation.recommended_provider = provider
            recommendation.estimated_monthly_savings = float(recommendation_savings)
            recommendation.priority = priority
        else:
            recommendation = Recommendation(
                user_id=user.id,
                dataset_id=dataset_id,
                resource_name=recommendation_resource_name,
                current_tier=current_tier,
                recommended_tier=recommended_tier,
                recommended_provider=provider,
                estimated_monthly_savings=float(recommendation_savings),
                priority=priority,
                status=RecommendationStatus.OPEN,
            )
            self.db.add(recommendation)

    def _extract_row_and_metadata(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        row = payload.get("record")
        metadata = payload.get("metadata")
        if isinstance(row, dict):
            return row, metadata if isinstance(metadata, dict) else {}
        return payload, metadata if isinstance(metadata, dict) else {}

    def _nested(self, payload: dict[str, Any], *path: str) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _map_provider(self, raw: Any) -> CloudProvider:
        value = str(raw).strip().upper()
        if value in {"AWS", "AZURE", "GCP", "MULTI"}:
            return CloudProvider(value)
        return CloudProvider.MULTI

    def _map_temperature(self, raw: Any) -> DataTemperature | None:
        value = str(raw).strip().upper()
        if value in {"HOT", "COLD", "ARCHIVE"}:
            return DataTemperature(value)
        return None

    def _to_float(self, raw: Any) -> float:
        try:
            return float(raw)
        except Exception:
            return 0.0

    def _to_int(self, raw: Any) -> int | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            return None

    def _to_float_strict(self, raw: Any, field_name: str) -> float:
        if raw is None:
            raise ValueError(f"Missing required feature '{field_name}' for ML classification")
        if isinstance(raw, str) and not raw.strip():
            raise ValueError(f"Missing required feature '{field_name}' for ML classification")
        try:
            value = float(raw)
        except Exception as exc:  # pragma: no cover - defensive conversion guard
            raise ValueError(f"Invalid numeric value for feature '{field_name}'") from exc
        if not math.isfinite(value):
            raise ValueError(f"Invalid numeric value for feature '{field_name}'")
        return value

    def _required_number(
        self,
        *,
        row: dict[str, Any],
        payload: dict[str, Any],
        field_name: str,
        paths: list[tuple[str, ...]],
        min_value: float = 0.0,
        strict_gt: bool = False,
    ) -> float:
        for path in paths:
            candidate = self._nested(row, *path)
            if candidate is None:
                candidate = self._nested(payload, *path)
            if candidate is None:
                candidate = self._nested(payload, "record", *path)
            if candidate is None:
                continue
            if isinstance(candidate, str) and not candidate.strip():
                continue
            numeric = self._to_float_strict(candidate, field_name)
            return self._validate_number_range(
                field_name=field_name,
                value=numeric,
                min_value=min_value,
                strict_gt=strict_gt,
            )
        raise ValueError(f"Missing required feature '{field_name}' for ML classification")

    def _optional_number(
        self,
        *,
        row: dict[str, Any],
        payload: dict[str, Any],
        field_name: str,
        paths: list[tuple[str, ...]],
        min_value: float = 0.0,
        strict_gt: bool = False,
    ) -> float | None:
        for path in paths:
            candidate = self._nested(row, *path)
            if candidate is None:
                candidate = self._nested(payload, *path)
            if candidate is None:
                candidate = self._nested(payload, "record", *path)
            if candidate is None:
                continue
            if isinstance(candidate, str) and not candidate.strip():
                continue
            try:
                numeric = self._to_float_strict(candidate, field_name)
                return self._validate_number_range(
                    field_name=field_name,
                    value=numeric,
                    min_value=min_value,
                    strict_gt=strict_gt,
                )
            except ValueError:
                continue
        return None

    def _fallback_latency_ms(
        self,
        *,
        row: dict[str, Any],
        payload: dict[str, Any],
        requests_30d: float,
    ) -> float:
        temperature_hint = self._map_temperature(
            row.get("temperature")
            or row.get("data_temperature")
            or row.get("tier_category")
            or row.get("tier")
            or row.get("class")
            or self._nested(payload, "temperature")
            or self._nested(payload, "data_temperature")
        )
        if temperature_hint == DataTemperature.HOT:
            return 120.0
        if temperature_hint == DataTemperature.COLD:
            return 320.0
        if temperature_hint == DataTemperature.ARCHIVE:
            return 900.0

        tier_hint = str(
            row.get("predicted_tier")
            or row.get("ml_predicted_tier")
            or row.get("ML_predicted_tier")
            or row.get("recommended_tier")
            or self._nested(payload, "ml", "predicted_tier")
            or self._nested(payload, "ml_prediction", "tier")
            or ""
        ).strip().lower()
        if any(token in tier_hint for token in ("archive", "glacier", "deep")):
            return 900.0
        if any(token in tier_hint for token in ("cool", "cold", "ia", "nearline", "coldline")):
            return 320.0
        if any(token in tier_hint for token in ("hot", "standard")):
            return 120.0

        if requests_30d > 40_000:
            return 120.0
        if requests_30d > 500:
            return 320.0
        return 900.0

    def _temperature_tier_from_signals(
        self,
        *,
        requests_30d: float,
        requests_90d: float | None,
        last_access_days: float | None,
        read_write_ratio: float | None,
        access_std_dev: float | None,
        object_size_bytes: float,
        retrieval_cost_per_gb: float | None,
    ) -> str | None:
        if last_access_days is None or read_write_ratio is None or access_std_dev is None:
            return None

        recency_score = math.exp(-float(last_access_days) / 30.0)
        access_volatility = float(access_std_dev) / (float(requests_30d) + 1.0)
        read_write_ratio = max(0.1, min(10.0, float(read_write_ratio)))
        requests_90d_value = requests_90d if requests_90d is not None else float(requests_30d) * 3.0
        momentum_denominator = max(float(requests_90d_value) / 3.0, 1e-6)
        momentum = float(requests_30d) / momentum_denominator
        momentum = max(0.2, min(2.0, momentum))

        temperature_raw = (
            0.40 * math.log10(float(requests_30d) + 1.0)
            + 0.25 * recency_score
            + 0.15 * read_write_ratio
            + 0.10 * momentum
            - 0.10 * access_volatility
        )
        temperature_score = self._normalize_temperature(temperature_raw)
        tier = self._temperature_band(temperature_score)

        archive_guardrail = False
        if last_access_days < 7:
            tier = "HOT"
        if last_access_days < 30 and tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            tier = "COLD"
            archive_guardrail = True
        if requests_30d > self.ARCHIVE_REQUESTS_THRESHOLD and tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            tier = "COLD"
            archive_guardrail = True

        object_size_tb = object_size_bytes / (1024.0 ** 4) if object_size_bytes > 0 else 0.0
        retrieval_penalty_high = False
        if retrieval_cost_per_gb is not None and retrieval_cost_per_gb > 0 and object_size_bytes > 0:
            object_size_gb = object_size_bytes / (1024.0 ** 3)
            retrieval_penalty = object_size_gb * float(retrieval_cost_per_gb)
            retrieval_penalty_high = retrieval_penalty >= self.RETRIEVAL_PENALTY_HIGH
        if object_size_tb > self.LARGE_OBJECT_TB and retrieval_penalty_high and tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            tier = "COLD"
            archive_guardrail = True

        lifecycle_tier = self._lifecycle_tier(last_access_days=int(last_access_days))
        final_tier = self._coldest_tier(tier, lifecycle_tier)
        if archive_guardrail and final_tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            final_tier = "COLD"
        return final_tier

    def _normalize_temperature(self, raw_score: float) -> float:
        if self.TEMPERATURE_RAW_MAX <= 0:
            return 0.0
        normalized = (float(raw_score) / self.TEMPERATURE_RAW_MAX) * 10.0
        return max(0.0, min(10.0, normalized))

    @staticmethod
    def _temperature_band(score: float) -> str:
        if score >= 7.0:
            return "HOT"
        if score >= 5.0:
            return "WARM"
        if score >= 3.0:
            return "COLD"
        return "ARCHIVE"

    @staticmethod
    def _lifecycle_tier(*, last_access_days: int) -> str:
        if last_access_days < 30:
            return "HOT"
        if last_access_days < 90:
            return "WARM"
        if last_access_days < 180:
            return "COLD"
        if last_access_days < 365:
            return "ARCHIVE"
        return "DEEP_ARCHIVE"

    @staticmethod
    def _coldest_tier(tier_a: str, tier_b: str) -> str:
        order = {"HOT": 0, "WARM": 1, "COLD": 2, "ARCHIVE": 3, "DEEP_ARCHIVE": 4}
        return tier_a if order.get(tier_a, 0) >= order.get(tier_b, 0) else tier_b

    @staticmethod
    def _map_tier_to_temperature(tier: str) -> DataTemperature:
        if tier == "HOT":
            return DataTemperature.HOT
        if tier in {"ARCHIVE", "DEEP_ARCHIVE"}:
            return DataTemperature.ARCHIVE
        return DataTemperature.COLD

    def _validate_number_range(
        self,
        *,
        field_name: str,
        value: float,
        min_value: float = 0.0,
        strict_gt: bool = False,
    ) -> float:
        if strict_gt:
            if value <= min_value:
                raise ValueError(f"Feature '{field_name}' must be > {min_value}")
            return value
        if value < min_value:
            raise ValueError(f"Feature '{field_name}' must be >= {min_value}")
        return value

    def _days_since(self, raw: Any) -> float:
        if raw is None:
            return 0.0
        text = str(raw).strip()
        if not text:
            return 0.0
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = now - parsed.astimezone(UTC)
        return max(delta.total_seconds() / 86400.0, 0.0)

    def _as_str(self, raw: Any) -> str:
        if raw is None:
            return ""
        value = str(raw).strip()
        return value

    def _resolve_bucket_id(
        self,
        *,
        row: dict[str, Any],
        payload: dict[str, Any],
        metadata: dict[str, Any],
        provider: CloudProvider,
        resource_name: str,
    ) -> str:
        bucket = (
            self._as_str(row.get("bucket_id"))
            or self._as_str(row.get("bucket"))
            or self._as_str(row.get("bucket_name"))
            or self._as_str(row.get("container"))
            or self._as_str(row.get("container_name"))
            or self._as_str(row.get("dataset"))
            or self._as_str(self._nested(payload, "bucket_id"))
            or self._as_str(self._nested(payload, "bucket"))
            or self._as_str(self._nested(payload, "record", "bucket_id"))
            or self._as_str(self._nested(payload, "record", "bucket"))
            or self._as_str(metadata.get("bucket_id"))
            or self._as_str(metadata.get("bucket"))
        )
        if bucket:
            return bucket
        provider_prefix = provider.value.lower()
        return f"{provider_prefix}::{resource_name}"

    def _derive_monthly_cost_from_storage_class(self, *, size_mb: float, storage_class: str) -> float:
        if size_mb <= 0:
            return 0.0
        storage_gb = max(size_mb / 1024.0, 0.0)
        rate = self.BASE_STORAGE_RATES.get(
            self._normalize_storage_class(storage_class),
            self.BASE_STORAGE_RATES["STANDARD"],
        )
        return round(storage_gb * rate, 4)

    def _normalize_storage_class(self, storage_class: str) -> str:
        text = str(storage_class or "").strip().upper()
        text = text.replace("_", " ").replace("-", " ")
        text = " ".join(text.split())
        aliases = {
            "STANDARD": "STANDARD",
            "S3 STANDARD": "STANDARD",
            "HOT BLOB": "STANDARD",
            "STANDARD IA": "STANDARD-IA",
            "STANDARDIA": "STANDARD-IA",
            "S3 STANDARD IA": "STANDARD-IA",
            "INFREQUENT ACCESS": "STANDARD-IA",
            "ONE ZONE IA": "STANDARD-IA",
            "NEARLINE": "STANDARD-IA",
            "COOL BLOB": "COOL BLOB",
            "COOL": "COOL BLOB",
            "ARCHIVE": "ARCHIVE",
            "ARCHIVE BLOB": "ARCHIVE",
            "GLACIER": "ARCHIVE",
            "DEEP ARCHIVE": "ARCHIVE",
        }
        return aliases.get(text, "STANDARD")

    async def sync_official_api_source(
        self,
        *,
        user: User,
        source_name: str,
        provider: str,
        endpoint_url: str,
        auth_type: str,
        auth_token: str | None,
        incremental_cursor: str | None,
        estimated_cost_per_call: Decimal,
    ) -> tuple[DataSource, list[IngestedRecord], str | None, Decimal]:
        source = self._ensure_data_source(
            user_id=user.id,
            source_type=DataSourceType.OFFICIAL_API,
            provider=provider,
            name=source_name,
            auth_config={"auth_type": auth_type},
        )

        headers: dict[str, str] = {}
        if auth_type == "api_key" and auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if incremental_cursor:
            headers["X-Incremental-Cursor"] = incremental_cursor

        payload = await self._fetch_payload_with_retry(endpoint_url=endpoint_url, headers=headers)
        records_payload = payload.get("data", [])
        if not isinstance(records_payload, list):
            records_payload = [records_payload]

        ingested: list[IngestedRecord] = []
        for item in records_payload:
            if not isinstance(item, dict):
                continue
            record = self.ingest_user_payload(
                user=user,
                api_key=None,
                payload=item,
                schema_version="v1",
                external_id=str(item.get("id", "")) or None,
                idempotency_key=str(item.get("id", "")) or None,
                method=IngestionMethod.OFFICIAL_API,
            )
            record.data_source_id = source.id
            ingested.append(record)

        next_cursor = payload.get("next_cursor")
        source.sync_cursor = str(next_cursor) if next_cursor else incremental_cursor
        source.last_synced_at = datetime.now(UTC)
        source.ingestion_cost = Decimal(source.ingestion_cost) + (
            Decimal(estimated_cost_per_call) * Decimal(max(len(ingested), 1))
        )
        self.db.commit()
        self.db.refresh(source)

        total_cost = Decimal(estimated_cost_per_call) * Decimal(max(len(ingested), 1))
        return source, ingested, source.sync_cursor, total_cost

    def receive_webhook_event(
        self,
        *,
        provider: str,
        event_id: str,
        payload: dict[str, Any],
        signature: str | None,
        user_id: int | None = None,
    ) -> WebhookEvent:
        existing = self.db.scalar(
            select(WebhookEvent).where(WebhookEvent.provider == provider, WebhookEvent.event_id == event_id)
        )
        if existing:
            return existing

        event = WebhookEvent(
            provider=provider,
            event_id=event_id,
            user_id=user_id,
            signature=signature,
            payload=payload,
            status=WebhookProcessStatus.RECEIVED,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def process_webhook_event(self, event: WebhookEvent) -> None:
        try:
            user_id = event.user_id or int(event.payload.get("user_id", 0) or 0)
            if not user_id:
                event.status = WebhookProcessStatus.FAILED
                event.error_message = "Webhook event missing user_id"
                self.db.commit()
                return

            user = self.db.scalar(select(User).where(User.id == user_id))
            if not user:
                event.status = WebhookProcessStatus.FAILED
                event.error_message = "User not found for webhook event"
                self.db.commit()
                return

            payload = event.payload.get("data")
            if not isinstance(payload, dict):
                payload = {"raw": event.payload}
            self.ingest_user_payload(
                user=user,
                api_key=None,
                payload=payload,
                schema_version="v1",
                external_id=str(event.payload.get("id", "")) or None,
                idempotency_key=f"{event.provider}:{event.event_id}",
                method=IngestionMethod.WEBHOOK,
            )
            event.status = WebhookProcessStatus.PROCESSED
            event.processed_at = datetime.now(UTC)
            event.error_message = None
            self.db.commit()
        except Exception as exc:
            event.status = WebhookProcessStatus.FAILED
            event.error_message = str(exc)
            self.db.commit()

    def _ensure_data_source(
        self,
        *,
        user_id: int | None,
        source_type: DataSourceType,
        provider: str,
        name: str,
        auth_config: dict[str, Any] | None,
    ) -> DataSource:
        source = self.db.scalar(
            select(DataSource).where(
                DataSource.user_id == user_id,
                DataSource.source_type == source_type,
                DataSource.provider == provider,
                DataSource.name == name,
            )
        )
        if source:
            return source

        source = DataSource(
            user_id=user_id,
            source_type=source_type,
            provider=provider,
            name=name,
            auth_config=auth_config or {},
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    async def _fetch_payload(self, *, endpoint_url: str, headers: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(endpoint_url, headers=headers)
            if response.status_code == 429:
                raise ValueError("Rate limited by upstream API")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return {"data": data}
            return data

    async def _fetch_payload_with_retry(self, *, endpoint_url: str, headers: dict[str, str]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.OFFICIAL_API_MAX_ATTEMPTS + 1):
            try:
                return await self._fetch_payload(endpoint_url=endpoint_url, headers=headers)
            except Exception as exc:
                last_exc = exc
                if attempt == self.OFFICIAL_API_MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(min(2 ** attempt, 10))
        if last_exc:
            raise last_exc
        return {"data": []}

    def _normalize_payload(self, *, payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
        normalized = {
            "schema_version": schema_version,
            "normalized_at": datetime.now(UTC).isoformat(),
            "attributes": payload,
            "keys": sorted(payload.keys()),
        }
        return normalized

    def _content_hash(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
