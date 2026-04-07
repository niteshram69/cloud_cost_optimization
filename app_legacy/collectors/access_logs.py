"""Access log ingestion for usage-frequency derivation.

The parser accepts normalized or provider-specific dictionaries and emits
normalized access event records.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.collectors.models import AccessEventRecord, AccessOperation


class AccessLogCollector:
    """Transforms cloud access logs into normalized event records."""

    def parse_events(self, raw_events: list[dict]) -> list[AccessEventRecord]:
        """Parse provider logs into normalized `AccessEventRecord` objects."""
        normalized: list[AccessEventRecord] = []
        for raw in raw_events:
            provider = str(raw.get("provider", "aws")).lower()
            operation = self._normalize_operation(str(raw.get("operation", "read")))
            timestamp = self._parse_timestamp(raw.get("timestamp"))

            event = AccessEventRecord(
                tenant_id=str(raw.get("tenant_id", "default")),
                provider=provider,
                region=str(raw.get("region", "us-east-1")),
                bucket=str(raw.get("bucket", "")),
                object_key=str(raw.get("object_key", "")),
                event_id=str(raw.get("event_id") or f"{provider}-{len(normalized)}"),
                operation=operation,
                timestamp=timestamp,
                bytes_transferred=int(raw.get("bytes_transferred", 0) or 0),
            )
            if event.bucket and event.object_key:
                normalized.append(event)

        return normalized

    @staticmethod
    def _parse_timestamp(value: object) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)

        raw = str(value or "").strip()
        if not raw:
            return datetime.now(UTC)

        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _normalize_operation(value: str) -> AccessOperation:
        lowered = value.lower()
        if lowered in {"get", "getobject", "read", "download", "list", "head"}:
            if lowered == "list":
                return AccessOperation.LIST
            return AccessOperation.READ
        if lowered in {"put", "post", "write", "upload", "copy"}:
            return AccessOperation.WRITE
        if lowered in {"delete", "remove"}:
            return AccessOperation.DELETE
        return AccessOperation.READ
