from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
from typing import Any

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import CloudProvider, DataTemperature, PricingIngestionRun, StoragePricingRecord, StorageRecord
from backend.app.services.canonical_tier_mapping_service import CanonicalTierMappingService

logger = logging.getLogger(__name__)

# Canonical tier mapping is sourced from DB lookup table via CanonicalTierMappingService.


@dataclass(slots=True)
class PricingDecisionInput:
    resource_id: str
    data_temperature: DataTemperature
    storage_gb: float
    monthly_retrieval_gb: float
    region_preference: str | None
    current_cloud: str | None
    current_tier: str | None
    current_monthly_cost: float | None
    currency: str


@dataclass(slots=True)
class PricingDecisionCandidate:
    cloud: str
    native_tier: str
    canonical_tier: str
    region: str
    storage_price_per_gb: float
    retrieval_price_per_gb: float
    monthly_cost: float
    currency: str


@dataclass(slots=True)
class PricingDecisionResult:
    resource_id: str
    data_temperature: str
    current_cloud: str | None
    current_tier: str | None
    recommended_cloud: str
    recommended_tier: str
    current_monthly_cost: float
    optimized_monthly_cost: float
    estimated_savings_percent: float
    pricing_version: str
    currency: str
    region_preference: str | None
    candidates: list[PricingDecisionCandidate]
    cost_assumptions: dict[str, str]
    explanation: str


class AzurePricingIngestionService:
    """Ingest and normalize Azure Storage retail pricing into canonical tiers."""

    def __init__(self, db: Session):
        self.db = db
        self.source_url = settings.azure_pricing_url
        self.mapping_service = CanonicalTierMappingService(db)

    async def sync_latest(self, *, max_pages: int | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        pricing_version = now.date().isoformat()
        existing_count = int(
            self.db.scalar(
                select(func.count(StoragePricingRecord.id)).where(
                    StoragePricingRecord.cloud == CloudProvider.AZURE,
                    StoragePricingRecord.pricing_version == pricing_version,
                )
            )
            or 0
        )
        if existing_count > 0:
            run = PricingIngestionRun(
                cloud=CloudProvider.AZURE,
                provider_feed="azure-retail-prices",
                pricing_version=pricing_version,
                source_url=self.source_url,
                status="SKIPPED_EXISTING_VERSION",
                records_inserted=0,
                started_at=now,
                completed_at=datetime.now(UTC),
            )
            self.db.add(run)
            self.db.commit()
            return {
                "cloud": CloudProvider.AZURE.value,
                "pricing_version": pricing_version,
                "records_inserted": 0,
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }

        run = PricingIngestionRun(
            cloud=CloudProvider.AZURE,
            provider_feed="azure-retail-prices",
            pricing_version=pricing_version,
            source_url=self.source_url,
            status="RUNNING",
            records_inserted=0,
            started_at=now,
        )
        self.db.add(run)
        self.db.flush()

        try:
            items = await self._fetch_azure_storage_items(max_pages=max_pages)
            normalized = self._normalize_azure_items(items=items, pricing_version=pricing_version)
            for record in normalized:
                self.db.add(record)

            run.records_inserted = len(normalized)
            run.status = "COMPLETED"
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(run)
            return {
                "cloud": CloudProvider.AZURE.value,
                "pricing_version": pricing_version,
                "records_inserted": len(normalized),
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }
        except Exception as exc:
            self.db.rollback()
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            self.db.add(run)
            self.db.commit()
            raise

    async def _fetch_azure_storage_items(self, *, max_pages: int | None = None) -> list[dict[str, Any]]:
        params = {"$filter": "serviceName eq 'Storage' and priceType eq 'Consumption'"}
        items: list[dict[str, Any]] = []
        next_url: str | None = self.source_url
        page_index = 0
        page_limit = max(1, max_pages or settings.pricing_max_pages)

        async with httpx.AsyncClient(timeout=settings.pricing_request_timeout_seconds) as client:
            while next_url and page_index < page_limit:
                if page_index == 0:
                    response = await client.get(next_url, params=params)
                else:
                    response = await client.get(next_url)
                response.raise_for_status()
                payload = response.json()
                page_items = payload.get("Items", [])
                if isinstance(page_items, list):
                    items.extend(item for item in page_items if isinstance(item, dict))
                next_url = payload.get("NextPageLink")
                page_index += 1

        if page_index >= page_limit and next_url:
            logger.warning("Azure pricing sync hit page limit (%s); results truncated", page_limit)

        if not items:
            raise ValueError("Azure pricing API returned no storage items")
        return items

    def _normalize_azure_items(
        self,
        *,
        items: list[dict[str, Any]],
        pricing_version: str,
    ) -> list[StoragePricingRecord]:
        grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        fallback_effective_date = datetime.now(UTC).date()

        for item in items:
            service_name = str(item.get("serviceName") or "").strip().lower()
            if service_name != "storage":
                continue

            product_name = str(item.get("productName") or "").strip()
            meter_name = str(item.get("meterName") or "").strip()
            region = str(item.get("armRegionName") or item.get("location") or "").strip().lower()
            if not region:
                continue
            currency = str(item.get("currencyCode") or "USD").strip().upper() or "USD"
            unit_price = self._to_float(item.get("unitPrice"))
            if unit_price <= 0:
                continue

            native_tier = self._map_azure_native_tier(product_name=product_name, meter_name=meter_name)
            if native_tier is None:
                continue
            canonical_tier = self.mapping_service.resolve(cloud=CloudProvider.AZURE, native_tier=native_tier)
            if canonical_tier is None:
                continue

            meter_kind = self._classify_meter_kind(
                unit=str(item.get("unitOfMeasure") or ""),
                product_name=product_name,
                meter_name=meter_name,
            )
            if meter_kind is None:
                continue

            key = (
                canonical_tier.value,
                native_tier,
                region,
                currency,
            )
            bucket = grouped.setdefault(
                key,
                {
                    "storage_price_per_gb": None,
                    "retrieval_price_per_gb": 0.0,
                    "effective_date": self._parse_effective_date(item.get("effectiveStartDate"), fallback_effective_date),
                    "source_offer_id": str(item.get("skuId") or item.get("meterId") or "")[:255] or None,
                    "source_payload": item,
                },
            )

            if meter_kind == "storage":
                current = bucket["storage_price_per_gb"]
                if current is None or unit_price < float(current):
                    bucket["storage_price_per_gb"] = unit_price
                    bucket["source_offer_id"] = str(item.get("skuId") or item.get("meterId") or "")[:255] or None
                    bucket["source_payload"] = item
                    bucket["effective_date"] = self._parse_effective_date(
                        item.get("effectiveStartDate"),
                        fallback_effective_date,
                    )
            elif meter_kind == "retrieval":
                current_retrieval = float(bucket.get("retrieval_price_per_gb", 0.0) or 0.0)
                if current_retrieval <= 0.0 or unit_price < current_retrieval:
                    bucket["retrieval_price_per_gb"] = unit_price

        records: list[StoragePricingRecord] = []
        for (canonical_tier, native_tier, region, currency), bucket in grouped.items():
            storage_price = bucket.get("storage_price_per_gb")
            if storage_price is None:
                continue
            records.append(
                StoragePricingRecord(
                    cloud=CloudProvider.AZURE,
                    service="blob",
                    canonical_tier=DataTemperature(canonical_tier),
                    native_tier=native_tier,
                    region=region,
                    storage_price_per_gb=float(storage_price),
                    retrieval_price_per_gb=float(bucket.get("retrieval_price_per_gb", 0.0) or 0.0),
                    currency=currency,
                    pricing_version=pricing_version,
                    effective_date=bucket["effective_date"],
                    source_offer_id=bucket.get("source_offer_id"),
                    source_payload=bucket.get("source_payload"),
                )
            )
        if not records:
            raise ValueError("No Azure storage pricing records could be normalized from retail API payload")
        return records

    def _map_azure_native_tier(self, *, product_name: str, meter_name: str) -> str | None:
        text = f"{product_name} {meter_name}".lower()
        if "archive" in text:
            return "Archive Blob"
        if "cool" in text:
            return "Cool Blob"
        if "hot" in text:
            return "Hot Blob"
        return None

    def _classify_meter_kind(self, *, unit: str, product_name: str, meter_name: str) -> str | None:
        unit_l = unit.strip().lower()
        text = f"{product_name} {meter_name}".lower()
        has_gb_unit = "gb" in unit_l or "gib" in unit_l
        if not has_gb_unit:
            return None
        if "retrieval" in text:
            return "retrieval"
        if "read" in text and "data" in text:
            return "retrieval"
        if "operation" in text:
            return None
        if "stored" in text or "storage" in text or "capacity" in text or "month" in unit_l:
            return "storage"
        return None

    def _parse_effective_date(self, value: Any, fallback: date) -> date:
        if not value:
            return fallback
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return fallback

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0


class AWSPricingIngestionService:
    """Ingest and normalize AWS S3 pricing feed into canonical storage tiers."""

    def __init__(self, db: Session):
        self.db = db
        self.source_url = settings.aws_s3_pricing_url
        self.mapping_service = CanonicalTierMappingService(db)

    async def sync_latest(self, *, max_records: int | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        pricing_version = now.date().isoformat()
        existing_count = int(
            self.db.scalar(
                select(func.count(StoragePricingRecord.id)).where(
                    StoragePricingRecord.cloud == CloudProvider.AWS,
                    StoragePricingRecord.pricing_version == pricing_version,
                )
            )
            or 0
        )
        if existing_count > 0:
            run = PricingIngestionRun(
                cloud=CloudProvider.AWS,
                provider_feed="aws-amazon-s3-offer",
                pricing_version=pricing_version,
                source_url=self.source_url,
                status="SKIPPED_EXISTING_VERSION",
                records_inserted=0,
                started_at=now,
                completed_at=datetime.now(UTC),
            )
            self.db.add(run)
            self.db.commit()
            return {
                "cloud": CloudProvider.AWS.value,
                "pricing_version": pricing_version,
                "records_inserted": 0,
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }

        run = PricingIngestionRun(
            cloud=CloudProvider.AWS,
            provider_feed="aws-amazon-s3-offer",
            pricing_version=pricing_version,
            source_url=self.source_url,
            status="RUNNING",
            records_inserted=0,
            started_at=now,
        )
        self.db.add(run)
        self.db.flush()

        try:
            payload = await self._fetch_offer()
            normalized = self._normalize_offer(
                payload=payload,
                pricing_version=pricing_version,
                max_records=max_records,
            )
            for record in normalized:
                self.db.add(record)

            run.records_inserted = len(normalized)
            run.status = "COMPLETED"
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(run)
            return {
                "cloud": CloudProvider.AWS.value,
                "pricing_version": pricing_version,
                "records_inserted": len(normalized),
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }
        except Exception as exc:
            self.db.rollback()
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            self.db.add(run)
            self.db.commit()
            raise

    async def _fetch_offer(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=settings.pricing_request_timeout_seconds * 2) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("AWS pricing feed payload is invalid")
        return payload

    def _normalize_offer(
        self,
        *,
        payload: dict[str, Any],
        pricing_version: str,
        max_records: int | None,
    ) -> list[StoragePricingRecord]:
        products = payload.get("products", {})
        on_demand = payload.get("terms", {}).get("OnDemand", {})
        if not isinstance(products, dict) or not isinstance(on_demand, dict):
            raise ValueError("AWS pricing feed missing products/terms")

        storage_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        retrieval_map: dict[tuple[str, str, str], float] = {}
        fallback_effective_date = self._parse_effective_date(payload.get("publicationDate"), datetime.now(UTC).date())

        for sku, product in products.items():
            if not isinstance(product, dict):
                continue
            attributes = product.get("attributes")
            if not isinstance(attributes, dict):
                continue
            native_tier = self._map_aws_native_tier(attributes)
            if not native_tier:
                continue
            canonical_tier = self.mapping_service.resolve(cloud=CloudProvider.AWS, native_tier=native_tier)
            if canonical_tier is None:
                continue
            region = self._extract_aws_region(attributes)

            term_group = on_demand.get(sku)
            if not isinstance(term_group, dict):
                continue

            for _, offer_term in term_group.items():
                if not isinstance(offer_term, dict):
                    continue
                price_dimensions = offer_term.get("priceDimensions")
                if not isinstance(price_dimensions, dict):
                    continue

                for _, dimension in price_dimensions.items():
                    if not isinstance(dimension, dict):
                        continue
                    unit = str(dimension.get("unit") or "")
                    desc_text = str(dimension.get("description") or "")
                    meter_kind = self._classify_aws_meter_kind(
                        attributes=attributes,
                        unit=unit,
                        description=desc_text,
                    )
                    if meter_kind is None:
                        continue

                    price_per_unit = dimension.get("pricePerUnit")
                    currency = "USD"
                    value = 0.0
                    if isinstance(price_per_unit, dict):
                        if "USD" in price_per_unit:
                            value = self._to_float(price_per_unit.get("USD"))
                            currency = "USD"
                        else:
                            first_currency = next(iter(price_per_unit.items()), None)
                            if first_currency is None:
                                continue
                            currency, raw_value = first_currency
                            value = self._to_float(raw_value)
                    if value <= 0:
                        continue

                    if meter_kind == "storage":
                        key = (canonical_tier.value, native_tier, region, currency.upper())
                        existing = storage_map.get(key)
                        if existing is None or value < float(existing["storage_price_per_gb"]):
                            storage_map[key] = {
                                "storage_price_per_gb": value,
                                "source_offer_id": str(sku),
                                "source_payload": dimension,
                                "effective_date": fallback_effective_date,
                            }
                    elif meter_kind == "retrieval":
                        retrieval_key = (native_tier, region, currency.upper())
                        current = retrieval_map.get(retrieval_key)
                        if current is None or value < current:
                            retrieval_map[retrieval_key] = value

        records: list[StoragePricingRecord] = []
        for (canonical_tier, native_tier, region, currency), bucket in storage_map.items():
            retrieval_price = retrieval_map.get((native_tier, region, currency), 0.0)
            records.append(
                StoragePricingRecord(
                    cloud=CloudProvider.AWS,
                    service="s3",
                    canonical_tier=DataTemperature(canonical_tier),
                    native_tier=native_tier,
                    region=region,
                    storage_price_per_gb=float(bucket["storage_price_per_gb"]),
                    retrieval_price_per_gb=float(retrieval_price),
                    currency=currency,
                    pricing_version=pricing_version,
                    effective_date=bucket["effective_date"],
                    source_offer_id=bucket.get("source_offer_id"),
                    source_payload=bucket.get("source_payload"),
                )
            )

        records.sort(key=lambda row: (row.canonical_tier.value, row.region, row.native_tier))
        if max_records is not None and max_records > 0:
            records = records[: max_records]
        if not records:
            raise ValueError("No AWS S3 pricing records could be normalized from AWS offer file")
        return records

    def _map_aws_native_tier(self, attributes: dict[str, Any]) -> str | None:
        text = " ".join(
            [
                str(attributes.get("storageClass") or ""),
                str(attributes.get("usagetype") or attributes.get("usageType") or ""),
                str(attributes.get("volumeType") or ""),
                str(attributes.get("operation") or ""),
                str(attributes.get("group") or ""),
            ]
        ).lower()

        if "deep archive" in text or "deeparchive" in text:
            return "Deep Archive"
        if "glacier" in text:
            return "Glacier"
        if "one zone" in text and "infrequent" in text:
            return "One Zone-IA"
        if "onezoneia" in text:
            return "One Zone-IA"
        if "standard-ia" in text or "standardia" in text or ("standard" in text and "infrequent" in text):
            return "Standard-IA"
        if "standard" in text and "intelligent" not in text:
            return "S3 Standard"
        return None

    def _extract_aws_region(self, attributes: dict[str, Any]) -> str:
        region = (
            str(attributes.get("regionCode") or "").strip()
            or str(attributes.get("location") or "").strip()
            or str(attributes.get("fromLocation") or "").strip()
            or "global"
        )
        return region.lower().replace(" ", "-")

    def _classify_aws_meter_kind(
        self,
        *,
        attributes: dict[str, Any],
        unit: str,
        description: str,
    ) -> str | None:
        unit_l = unit.strip().lower()
        text = " ".join(
            [
                str(attributes.get("usagetype") or attributes.get("usageType") or ""),
                str(attributes.get("operation") or ""),
                str(attributes.get("group") or ""),
                description,
            ]
        ).lower()
        has_gb = "gb" in unit_l
        if "retrieval" in text and has_gb:
            return "retrieval"
        if "request" in text or "operation" in text:
            return None
        if ("timedstorage" in text or "storage" in text or "archive" in text) and has_gb:
            return "storage"
        return None

    def _parse_effective_date(self, value: Any, fallback: date) -> date:
        if not value:
            return fallback
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return fallback

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0


class GCPPricingIngestionService:
    """Ingest and normalize GCP Cloud Billing catalog SKUs for Cloud Storage."""

    def __init__(self, db: Session):
        self.db = db
        service_id = settings.gcp_storage_service_id.strip()
        self.source_url = f"{settings.gcp_billing_catalog_url.rstrip('/')}/{service_id}/skus"
        self.mapping_service = CanonicalTierMappingService(db)

    async def sync_latest(self, *, max_pages: int | None = None, max_records: int | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        pricing_version = now.date().isoformat()
        existing_count = int(
            self.db.scalar(
                select(func.count(StoragePricingRecord.id)).where(
                    StoragePricingRecord.cloud == CloudProvider.GCP,
                    StoragePricingRecord.pricing_version == pricing_version,
                )
            )
            or 0
        )
        if existing_count > 0:
            run = PricingIngestionRun(
                cloud=CloudProvider.GCP,
                provider_feed="gcp-cloud-billing-catalog",
                pricing_version=pricing_version,
                source_url=self.source_url,
                status="SKIPPED_EXISTING_VERSION",
                records_inserted=0,
                started_at=now,
                completed_at=datetime.now(UTC),
            )
            self.db.add(run)
            self.db.commit()
            return {
                "cloud": CloudProvider.GCP.value,
                "pricing_version": pricing_version,
                "records_inserted": 0,
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }

        run = PricingIngestionRun(
            cloud=CloudProvider.GCP,
            provider_feed="gcp-cloud-billing-catalog",
            pricing_version=pricing_version,
            source_url=self.source_url,
            status="RUNNING",
            records_inserted=0,
            started_at=now,
        )
        self.db.add(run)
        self.db.flush()

        try:
            skus = await self._fetch_skus(max_pages=max_pages)
            normalized = self._normalize_skus(
                skus=skus,
                pricing_version=pricing_version,
                max_records=max_records,
            )
            for record in normalized:
                self.db.add(record)

            run.records_inserted = len(normalized)
            run.status = "COMPLETED"
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(run)
            return {
                "cloud": CloudProvider.GCP.value,
                "pricing_version": pricing_version,
                "records_inserted": len(normalized),
                "records_existing": existing_count,
                "source_url": self.source_url,
                "sync_started_at": run.started_at,
                "sync_completed_at": run.completed_at,
                "status": run.status,
            }
        except Exception as exc:
            self.db.rollback()
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            self.db.add(run)
            self.db.commit()
            raise

    async def _fetch_skus(self, *, max_pages: int | None) -> list[dict[str, Any]]:
        page_limit = max(1, max_pages or settings.pricing_max_pages)
        params: dict[str, Any] = {
            "currencyCode": "USD",
            "pageSize": 5000,
        }
        if settings.gcp_billing_api_key:
            params["key"] = settings.gcp_billing_api_key

        skus: list[dict[str, Any]] = []
        page_token: str | None = None
        page = 0
        async with httpx.AsyncClient(timeout=settings.pricing_request_timeout_seconds) as client:
            while page < page_limit:
                request_params = dict(params)
                if page_token:
                    request_params["pageToken"] = page_token
                response = await client.get(self.source_url, params=request_params)
                response.raise_for_status()
                payload = response.json()
                page_items = payload.get("skus", [])
                if isinstance(page_items, list):
                    skus.extend(item for item in page_items if isinstance(item, dict))
                page_token = payload.get("nextPageToken")
                page += 1
                if not page_token:
                    break
        if not skus:
            raise ValueError("GCP billing catalog returned no Cloud Storage SKUs")
        if page >= page_limit and page_token:
            logger.warning("GCP pricing sync hit page limit (%s); results truncated", page_limit)
        return skus

    def _normalize_skus(
        self,
        *,
        skus: list[dict[str, Any]],
        pricing_version: str,
        max_records: int | None,
    ) -> list[StoragePricingRecord]:
        storage_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        retrieval_map: dict[tuple[str, str, str], float] = {}
        fallback_effective_date = datetime.now(UTC).date()

        for sku in skus:
            description = str(sku.get("description") or "")
            category = sku.get("category")
            if not isinstance(category, dict):
                continue
            resource_family = str(category.get("resourceFamily") or "").lower()
            if resource_family != "storage":
                continue

            native_tier = self._map_gcp_native_tier(description)
            if native_tier is None:
                continue
            canonical_tier = self.mapping_service.resolve(cloud=CloudProvider.GCP, native_tier=native_tier)
            if canonical_tier is None:
                continue

            service_regions = sku.get("serviceRegions")
            regions = [str(region).strip().lower() for region in service_regions if str(region).strip()] if isinstance(service_regions, list) else []
            if not regions:
                regions = ["global"]

            pricing_info = sku.get("pricingInfo")
            if not isinstance(pricing_info, list) or not pricing_info:
                continue
            pricing_point = pricing_info[-1] if isinstance(pricing_info[-1], dict) else None
            if not pricing_point:
                continue

            pricing_expression = pricing_point.get("pricingExpression")
            if not isinstance(pricing_expression, dict):
                continue
            unit = str(pricing_expression.get("usageUnit") or pricing_expression.get("baseUnit") or "")
            meter_kind = self._classify_gcp_meter(description=description, unit=unit)
            if meter_kind is None:
                continue

            tiered_rates = pricing_expression.get("tieredRates")
            if not isinstance(tiered_rates, list) or not tiered_rates:
                continue
            first_rate = tiered_rates[0] if isinstance(tiered_rates[0], dict) else None
            if not first_rate:
                continue
            unit_price = first_rate.get("unitPrice")
            if not isinstance(unit_price, dict):
                continue
            value = self._gcp_money_to_float(unit_price)
            if value <= 0:
                continue

            currency = str(unit_price.get("currencyCode") or "USD").upper()
            effective_date = self._parse_effective_date(pricing_point.get("effectiveTime"), fallback_effective_date)

            for region in regions:
                if meter_kind == "storage":
                    key = (canonical_tier.value, native_tier, region, currency)
                    existing = storage_map.get(key)
                    if existing is None or value < float(existing["storage_price_per_gb"]):
                        storage_map[key] = {
                            "storage_price_per_gb": value,
                            "source_offer_id": str(sku.get("skuId") or "")[:255] or None,
                            "source_payload": sku,
                            "effective_date": effective_date,
                        }
                elif meter_kind == "retrieval":
                    retrieval_key = (native_tier, region, currency)
                    current = retrieval_map.get(retrieval_key)
                    if current is None or value < current:
                        retrieval_map[retrieval_key] = value

        records: list[StoragePricingRecord] = []
        for (canonical_tier, native_tier, region, currency), bucket in storage_map.items():
            retrieval_price = retrieval_map.get((native_tier, region, currency), 0.0)
            records.append(
                StoragePricingRecord(
                    cloud=CloudProvider.GCP,
                    service="cloud-storage",
                    canonical_tier=DataTemperature(canonical_tier),
                    native_tier=native_tier,
                    region=region,
                    storage_price_per_gb=float(bucket["storage_price_per_gb"]),
                    retrieval_price_per_gb=float(retrieval_price),
                    currency=currency,
                    pricing_version=pricing_version,
                    effective_date=bucket["effective_date"],
                    source_offer_id=bucket.get("source_offer_id"),
                    source_payload=bucket.get("source_payload"),
                )
            )

        records.sort(key=lambda row: (row.canonical_tier.value, row.region, row.native_tier))
        if max_records is not None and max_records > 0:
            records = records[: max_records]
        if not records:
            raise ValueError("No GCP Cloud Storage pricing records could be normalized from billing catalog")
        return records

    def _map_gcp_native_tier(self, description: str) -> str | None:
        text = description.lower()
        if "archive" in text:
            return "Archive"
        if "coldline" in text:
            return "Coldline"
        if "nearline" in text:
            return "Nearline"
        if "standard" in text:
            return "Standard"
        return None

    def _classify_gcp_meter(self, *, description: str, unit: str) -> str | None:
        text = description.lower()
        unit_l = unit.lower()
        has_data_unit = "gib" in unit_l or "gb" in unit_l
        if "retrieval" in text and has_data_unit:
            return "retrieval"
        if not has_data_unit:
            return None
        if "class a" in text or "class b" in text or "operation" in text or "request" in text:
            return None
        if "storage" in text or "stored data" in text:
            return "storage"
        return None

    def _gcp_money_to_float(self, money: dict[str, Any]) -> float:
        units = money.get("units")
        nanos = money.get("nanos")
        total = 0.0
        try:
            if units is not None:
                total += float(units)
            if nanos is not None:
                total += float(nanos) / 1_000_000_000.0
        except Exception:
            return 0.0
        return total

    def _parse_effective_date(self, value: Any, fallback: date) -> date:
        if not value:
            return fallback
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return fallback


class PricingDecisionService:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_version_metadata(self, *, currency: str = "USD") -> dict[str, Any] | None:
        currency_code = (currency or "USD").upper()
        latest_version = self.db.scalar(
            select(StoragePricingRecord.pricing_version)
            .where(StoragePricingRecord.currency == currency_code)
            .order_by(desc(StoragePricingRecord.effective_date), desc(StoragePricingRecord.created_at))
            .limit(1)
        )
        if not latest_version:
            return None

        stats = self.db.execute(
            select(
                func.count(StoragePricingRecord.id),
                func.max(StoragePricingRecord.created_at),
                func.max(StoragePricingRecord.effective_date),
            ).where(
                StoragePricingRecord.pricing_version == latest_version,
                StoragePricingRecord.currency == currency_code,
            )
        ).one()
        count, last_updated_at, effective_date = stats
        return {
            "cloud": "MULTI",
            "pricing_version": str(latest_version),
            "effective_date": effective_date,
            "currency": currency_code,
            "records_count": int(count or 0),
            "last_updated_at": last_updated_at,
        }

    def decide(self, request: PricingDecisionInput) -> PricingDecisionResult:
        currency = (request.currency or "USD").upper()
        version = self.db.scalar(
            select(StoragePricingRecord.pricing_version)
            .where(StoragePricingRecord.currency == currency)
            .order_by(desc(StoragePricingRecord.effective_date), desc(StoragePricingRecord.created_at))
            .limit(1)
        )
        if not version:
            raise ValueError("No pricing data available. Run Azure pricing sync first.")

        rows = self.db.scalars(
            select(StoragePricingRecord).where(
                StoragePricingRecord.pricing_version == version,
                StoragePricingRecord.currency == currency,
                StoragePricingRecord.canonical_tier == request.data_temperature,
            )
        ).all()
        if not rows:
            raise ValueError("No pricing candidates available for requested data temperature tier.")

        region_preference = self._normalize_region_preference(request.region_preference)
        filtered_rows = rows
        if region_preference:
            preferred = [row for row in rows if self._region_matches_preference(region_preference, row.region)]
            if preferred:
                filtered_rows = preferred

        candidates = [
            PricingDecisionCandidate(
                cloud=row.cloud.value,
                native_tier=row.native_tier,
                canonical_tier=row.canonical_tier.value,
                region=row.region,
                storage_price_per_gb=float(row.storage_price_per_gb),
                retrieval_price_per_gb=float(row.retrieval_price_per_gb),
                monthly_cost=round(
                    self.compute_monthly_cost(
                        storage_price_per_gb=float(row.storage_price_per_gb),
                        retrieval_price_per_gb=float(row.retrieval_price_per_gb),
                        storage_gb=request.storage_gb,
                        retrieval_gb=request.monthly_retrieval_gb,
                    ),
                    6,
                ),
                currency=currency,
            )
            for row in filtered_rows
        ]
        candidates.sort(key=lambda candidate: candidate.monthly_cost)

        best = candidates[0]
        current_cost = self._resolve_current_cost(request=request, candidates=candidates)
        optimized_cost = float(best.monthly_cost)
        savings_percent = round(((current_cost - optimized_cost) / current_cost) * 100, 2) if current_cost > 0 else 0.0
        if savings_percent < 0:
            savings_percent = 0.0

        explanation = (
            "Deterministic cost evaluation: monthly_cost = storage_gb * storage_price_per_gb + "
            "monthly_retrieval_gb * retrieval_price_per_gb. "
            f"Selected lowest candidate from {len(candidates)} options using pricing_version={version}."
        )
        monthly_access_rate = (
            (request.monthly_retrieval_gb / request.storage_gb) * 100.0 if request.storage_gb > 0 else 0.0
        )
        cost_assumptions = {
            "monthly_access_rate": f"{monthly_access_rate:.2f}%",
            "egress_costs": "excluded",
            "min_storage_duration": "honored",
        }

        return PricingDecisionResult(
            resource_id=request.resource_id,
            data_temperature=request.data_temperature.value,
            current_cloud=request.current_cloud,
            current_tier=request.current_tier,
            recommended_cloud=best.cloud,
            recommended_tier=best.native_tier,
            current_monthly_cost=round(current_cost, 6),
            optimized_monthly_cost=round(optimized_cost, 6),
            estimated_savings_percent=savings_percent,
            pricing_version=str(version),
            currency=currency,
            region_preference=request.region_preference,
            candidates=candidates,
            cost_assumptions=cost_assumptions,
            explanation=explanation,
        )

    def top_savings_opportunities(
        self,
        *,
        user_id: int,
        limit: int = 10,
        currency: str = "USD",
    ) -> dict[str, Any]:
        rows = self.db.scalars(
            select(StorageRecord)
            .where(StorageRecord.user_id == user_id)
            .order_by(StorageRecord.resource_name.asc(), StorageRecord.updated_at.desc(), StorageRecord.id.desc())
        ).all()

        latest_by_resource: dict[str, StorageRecord] = {}
        for row in rows:
            latest_by_resource.setdefault(row.resource_name, row)

        evaluated: list[dict[str, Any]] = []
        for record in latest_by_resource.values():
            current_cost = float(record.storage_cost or 0.0)
            if current_cost <= 0:
                continue
            try:
                decision = self.decide_for_storage_record(
                    resource_id=record.resource_name,
                    data_temperature=record.temperature,
                    region=record.region,
                    current_cloud=record.provider.value,
                    current_tier=record.temperature.value,
                    current_monthly_cost=current_cost,
                    currency=currency,
                )
            except ValueError:
                continue

            savings = round(max(decision.current_monthly_cost - decision.optimized_monthly_cost, 0.0), 4)
            if savings <= 0:
                continue
            evaluated.append(
                {
                    "resource_id": decision.resource_id,
                    "data_temperature": decision.data_temperature,
                    "current_cloud": record.provider.value,
                    "current_tier": record.temperature.value,
                    "recommended_cloud": decision.recommended_cloud,
                    "recommended_tier": decision.recommended_tier,
                    "region": record.region,
                    "current_monthly_cost": round(decision.current_monthly_cost, 4),
                    "optimized_monthly_cost": round(decision.optimized_monthly_cost, 4),
                    "monthly_savings": savings,
                    "estimated_savings_percent": round(decision.estimated_savings_percent, 2),
                    "pricing_version": decision.pricing_version,
                    "currency": decision.currency,
                }
            )

        evaluated.sort(key=lambda item: item["monthly_savings"], reverse=True)
        top_items = evaluated[: max(1, limit)]
        total_savings = round(sum(item["monthly_savings"] for item in top_items), 4)
        pricing_version = top_items[0]["pricing_version"] if top_items else (
            self.get_latest_version_metadata(currency=currency) or {}
        ).get("pricing_version", "")

        csv_headers = [
            "resource_id",
            "data_temperature",
            "current_cloud",
            "current_tier",
            "recommended_cloud",
            "recommended_tier",
            "region",
            "current_monthly_cost",
            "optimized_monthly_cost",
            "monthly_savings",
            "estimated_savings_percent",
            "pricing_version",
            "currency",
        ]
        csv_rows = [[str(item.get(col, "")) for col in csv_headers] for item in top_items]
        pdf_payload: dict[str, Any] = {
            "title": "Top Cross-Cloud Savings Opportunities",
            "generated_at": datetime.now(UTC).isoformat(),
            "pricing_version": str(pricing_version),
            "total_considered": len(latest_by_resource),
            "total_monthly_savings": total_savings,
            "items": top_items,
        }

        return {
            "total_considered": len(latest_by_resource),
            "total_monthly_savings": total_savings,
            "opportunities": top_items,
            "export": {
                "generated_at": datetime.now(UTC),
                "pricing_version": str(pricing_version),
                "csv_headers": csv_headers,
                "csv_rows": csv_rows,
                "pdf_payload": pdf_payload,
            },
        }

    def decide_for_storage_record(
        self,
        *,
        resource_id: str,
        data_temperature: DataTemperature,
        region: str,
        current_cloud: str | None,
        current_tier: str | None,
        current_monthly_cost: float,
        currency: str = "USD",
    ) -> PricingDecisionResult:
        storage_gb = self._estimate_storage_gb_from_cost(data_temperature=data_temperature, monthly_cost=current_monthly_cost)
        retrieval_gb = self._estimate_retrieval_gb(data_temperature=data_temperature, storage_gb=storage_gb)
        return self.decide(
            PricingDecisionInput(
                resource_id=resource_id,
                data_temperature=data_temperature,
                storage_gb=storage_gb,
                monthly_retrieval_gb=retrieval_gb,
                region_preference=region,
                current_cloud=current_cloud,
                current_tier=current_tier,
                current_monthly_cost=current_monthly_cost,
                currency=currency,
            )
        )

    def compute_monthly_cost(
        self,
        *,
        storage_price_per_gb: float,
        retrieval_price_per_gb: float,
        storage_gb: float,
        retrieval_gb: float,
    ) -> float:
        return max(storage_gb, 0.0) * max(storage_price_per_gb, 0.0) + max(retrieval_gb, 0.0) * max(retrieval_price_per_gb, 0.0)

    def _resolve_current_cost(
        self,
        *,
        request: PricingDecisionInput,
        candidates: list[PricingDecisionCandidate],
    ) -> float:
        if request.current_monthly_cost is not None:
            return float(request.current_monthly_cost)

        if request.current_cloud:
            cloud_candidates = [candidate for candidate in candidates if candidate.cloud.upper() == request.current_cloud.upper()]
            if request.current_tier:
                for candidate in cloud_candidates:
                    if candidate.native_tier.lower() == request.current_tier.lower():
                        return float(candidate.monthly_cost)
            if cloud_candidates:
                return float(min(cloud_candidates, key=lambda item: item.monthly_cost).monthly_cost)

        best = min(candidates, key=lambda item: item.monthly_cost).monthly_cost
        return float(best * 1.25)

    def _normalize_region_preference(self, region: str | None) -> str | None:
        if not region:
            return None
        value = region.strip().lower()
        if not value:
            return None
        if any(token in value for token in ("ap-", "asia", "india", "singapore", "japan", "korea", "australia")):
            return "asia"
        if any(token in value for token in ("eu-", "europe", "uk", "france", "germany", "sweden", "norway")):
            return "europe"
        if any(token in value for token in ("us-", "america", "canada", "brazil", "chile")):
            return "us"
        return value

    def _region_matches_preference(self, preference: str, region: str) -> bool:
        pref = preference.strip().lower()
        region_value = region.strip().lower()
        if not pref:
            return True
        if pref == "asia":
            tokens = ("asia", "ap-", "india", "japan", "korea", "singapore", "australia", "southeast", "eastasia")
            return any(token in region_value for token in tokens)
        if pref == "europe":
            tokens = ("eu-", "europe", "uk", "france", "germany", "sweden", "norway")
            return any(token in region_value for token in tokens)
        if pref == "us":
            tokens = ("us-", "northamerica", "southamerica", "america", "canada", "brazil", "chile")
            return any(token in region_value for token in tokens)
        return pref in region_value

    def _estimate_storage_gb_from_cost(
        self,
        *,
        data_temperature: DataTemperature,
        monthly_cost: float,
    ) -> float:
        baseline_rate = {
            DataTemperature.HOT: 0.023,
            DataTemperature.COLD: 0.0125,
            DataTemperature.ARCHIVE: 0.004,
        }[data_temperature]
        return max(float(monthly_cost) / baseline_rate, 1.0)

    def _estimate_retrieval_gb(
        self,
        *,
        data_temperature: DataTemperature,
        storage_gb: float,
    ) -> float:
        retrieval_ratio = {
            DataTemperature.HOT: 0.18,
            DataTemperature.COLD: 0.06,
            DataTemperature.ARCHIVE: 0.01,
        }[data_temperature]
        return round(storage_gb * retrieval_ratio, 6)
