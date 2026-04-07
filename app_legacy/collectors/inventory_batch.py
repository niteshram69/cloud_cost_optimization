"""Batch inventory collectors for legacy/backfill datasets.

This loader parses provider inventory exports and never reads object bodies.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime

from app.collectors.models import InventoryObjectRecord


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class InventoryBatchCollector:
    """Parses inventory rows into normalized metadata records."""

    def load_csv(self, report_path: str) -> list[InventoryObjectRecord]:
        """Load inventory metadata from CSV report."""
        records: list[InventoryObjectRecord] = []
        with open(report_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                tenant_id = row.get("tenant_id", "default").strip() or "default"
                provider = row.get("provider", "aws").strip().lower()
                region = row.get("region", "us-east-1").strip()
                bucket = row.get("bucket", "").strip()
                object_key = row.get("object_key", "").strip()
                storage_tier = row.get("storage_tier", "STANDARD").strip().upper()

                if not bucket or not object_key:
                    continue

                last_modified = _parse_dt(row.get("last_modified_at")) or datetime.now(UTC)
                last_accessed = _parse_dt(row.get("last_accessed_at"))

                metadata = {
                    "growth_bytes_90d": str(row.get("growth_bytes_90d", "0")).strip() or "0",
                    "source": "inventory_batch",
                }

                record = InventoryObjectRecord(
                    tenant_id=tenant_id,
                    provider=provider,
                    region=region,
                    bucket=bucket,
                    object_key=object_key,
                    storage_tier=storage_tier,
                    size_bytes=int(float(row.get("size_bytes", 0) or 0)),
                    last_modified_at=last_modified,
                    last_accessed_at=last_accessed,
                    etag=(row.get("etag") or "").strip() or None,
                    metadata=metadata,
                )
                records.append(record)

        return records
