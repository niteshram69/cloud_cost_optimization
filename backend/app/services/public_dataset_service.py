import csv
import io
import json
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.models import CloudProvider, DataTemperature, IngestionMethod, IngestedRecord, StorageRecord, User, UserRole
from backend.app.services.account_service import AccountService
from backend.app.services.ingestion_service import IngestionService
from backend.app.services.public_data_guard import PUBLIC_DATASET_COMPANY, PUBLIC_DATASET_EMAIL_DOMAIN


@dataclass(frozen=True)
class DatasetSource:
    key: str
    source_name: str
    provider_hint: CloudProvider
    description: str
    url: str | None
    format: str


PUBLIC_DATASET_SOURCES: dict[str, DatasetSource] = {
    "aws_cur_samples": DatasetSource(
        key="aws_cur_samples",
        source_name="AWS_CUR_SAMPLES",
        provider_hint=CloudProvider.AWS,
        description="AWS Cost and Usage Report sample rows for test workloads",
        # Public sample-like CSV from open source cloud billing examples.
        url="https://raw.githubusercontent.com/kubecost/cost-model/main/test/cloudcost/aws.csv",
        format="csv",
    ),
    "finops_foundation": DatasetSource(
        key="finops_foundation",
        source_name="FINOPS_FOUNDATION_DATASET",
        provider_hint=CloudProvider.MULTI,
        description="FinOps-style optimization datasets for benchmarking",
        url="https://raw.githubusercontent.com/kubecost/cost-model/main/test/cloudcost/mixed.csv",
        format="csv",
    ),
    "kaggle_cloud_cost": DatasetSource(
        key="kaggle_cloud_cost",
        source_name="KAGGLE_CLOUD_COST_SAMPLE",
        provider_hint=CloudProvider.MULTI,
        description="Kaggle-inspired cloud cost sample rows for safe testing",
        url=None,
        format="json",
    ),
}


class PublicDatasetService:
    def __init__(self, db: Session):
        self.db = db
        self.ingestion = IngestionService(db)

    def list_sources(self) -> list[DatasetSource]:
        return list(PUBLIC_DATASET_SOURCES.values())

    async def ingest(self, *, source_key: str, limit: int | None = None) -> dict[str, Any]:
        source = PUBLIC_DATASET_SOURCES.get(source_key)
        if not source:
            raise ValueError("Unknown public dataset source")

        rows = await self._load_rows(source=source, limit=limit or settings.public_dataset_max_rows)
        tenant_user = self._ensure_public_tenant(source=source)

        inserted = 0
        skipped = 0
        for idx, row in enumerate(rows):
            metadata = {
                "data_origin": "PUBLIC_DATASET",
                "source_name": source.source_name,
                "is_billable": False,
            }
            payload = {
                "metadata": metadata,
                "record": row,
            }

            try:
                record = self.ingestion.ingest_user_payload(
                    user=tenant_user,
                    api_key=None,
                    payload=payload,
                    schema_version="v1",
                    external_id=str(row.get("id", f"{source.key}-{idx}")),
                    idempotency_key=f"public:{source.key}:{idx}",
                    method=IngestionMethod.OFFICIAL_API,
                )
                self._upsert_storage_record(
                    user=tenant_user,
                    resource_name=f"{source.key}-{idx}",
                    row=row,
                    source=source,
                    record=record,
                )
                inserted += 1
            except ValueError:
                skipped += 1

        self.db.commit()
        return {
            "source_key": source.key,
            "source_name": source.source_name,
            "tenant_id": tenant_user.id,
            "inserted_records": inserted,
            "skipped_records": skipped,
            "is_billable": False,
        }

    def _ensure_public_tenant(self, *, source: DatasetSource) -> User:
        email = f"public+{source.key}@{PUBLIC_DATASET_EMAIL_DOMAIN}"
        existing = self.db.scalar(select(User).where(User.email == email))
        if existing:
            return existing

        user = User(
            name=f"Public Dataset Tenant ({source.source_name})",
            email=email,
            hashed_password=hash_password("PUBLIC_DATASET_DISABLED_LOGIN"),
            company_name=PUBLIC_DATASET_COMPANY,
            cloud_provider=source.provider_hint,
            role=UserRole.USER,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        account_service = AccountService(self.db)
        account_service.ensure_default_plans()
        account_service.ensure_user_account(user)
        return user

    async def _load_rows(self, *, source: DatasetSource, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if source.url:
            try:
                async with httpx.AsyncClient(timeout=settings.public_dataset_request_timeout_seconds) as client:
                    response = await client.get(source.url)
                    response.raise_for_status()
                    body = response.text
                rows = self._parse_rows(raw=body, fmt=source.format)
            except Exception:
                rows = []

        if not rows:
            rows = self._fallback_rows(source=source)

        return rows[:limit]

    def _parse_rows(self, *, raw: str, fmt: str) -> list[dict[str, Any]]:
        if fmt == "csv":
            reader = csv.DictReader(io.StringIO(raw))
            return [dict(row) for row in reader]
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _fallback_rows(self, *, source: DatasetSource) -> list[dict[str, Any]]:
        if source.key == "aws_cur_samples":
            return [
                {"id": "aws-001", "provider": "AWS", "region": "ap-south-1", "service": "S3", "monthly_cost": 124.2, "estimated_savings": 22.1, "temperature": "COLD"},
                {"id": "aws-002", "provider": "AWS", "region": "us-east-1", "service": "EC2", "monthly_cost": 310.8, "estimated_savings": 54.6, "temperature": "HOT"},
            ]
        if source.key == "finops_foundation":
            return [
                {"id": "finops-001", "provider": "AZURE", "region": "centralindia", "service": "Blob", "monthly_cost": 88.4, "estimated_savings": 19.2, "temperature": "ARCHIVE"},
                {"id": "finops-002", "provider": "GCP", "region": "asia-south1", "service": "Cloud Storage", "monthly_cost": 142.9, "estimated_savings": 27.9, "temperature": "COLD"},
            ]
        return [
            {"id": "kaggle-001", "provider": "MULTI", "region": "global", "service": "ObjectStorage", "monthly_cost": 77.7, "estimated_savings": 17.3, "temperature": "COLD"},
            {"id": "kaggle-002", "provider": "MULTI", "region": "global", "service": "Archive", "monthly_cost": 39.5, "estimated_savings": 10.1, "temperature": "ARCHIVE"},
        ]

    def _upsert_storage_record(
        self,
        *,
        user: User,
        resource_name: str,
        row: dict[str, Any],
        source: DatasetSource,
        record: IngestedRecord,
    ) -> None:
        existing = self.db.scalar(
            select(StorageRecord).where(StorageRecord.user_id == user.id, StorageRecord.resource_name == resource_name)
        )
        provider = self._map_provider(str(row.get("provider", source.provider_hint.value)))
        region = str(row.get("region", "global"))
        storage_cost = self._to_float(row.get("monthly_cost"), default=0.0)
        estimated_savings = self._to_float(row.get("estimated_savings"), default=0.0)
        temperature = self._map_temperature(str(row.get("temperature", "COLD")))
        confidence = self._to_float(row.get("confidence"), default=0.72)

        if existing:
            existing.provider = provider
            existing.region = region
            existing.storage_cost = storage_cost
            existing.estimated_savings = estimated_savings
            existing.temperature = temperature
            existing.classification_confidence = confidence
            return

        storage = StorageRecord(
            user_id=user.id,
            resource_name=resource_name,
            provider=provider,
            region=region,
            storage_cost=storage_cost,
            estimated_savings=estimated_savings,
            temperature=temperature,
            classification_confidence=confidence,
        )
        self.db.add(storage)

    def _map_provider(self, raw: str) -> CloudProvider:
        value = raw.strip().upper()
        if value in {"AWS", "AZURE", "GCP", "MULTI"}:
            return CloudProvider(value)
        return CloudProvider.MULTI

    def _map_temperature(self, raw: str) -> DataTemperature:
        value = raw.strip().upper()
        if value in {"HOT", "COLD", "ARCHIVE"}:
            return DataTemperature(value)
        return DataTemperature.COLD

    def _to_float(self, raw: Any, *, default: float) -> float:
        try:
            return float(raw)
        except Exception:
            return default
