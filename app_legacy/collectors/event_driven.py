"""Event-driven metadata and access-pattern collectors.

Designed for low API overhead: consume push-based events (S3 notifications,
Cloud Storage Pub/Sub, Azure Event Grid) instead of high-frequency polling.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.collectors.models import AccessEventRecord, AccessOperation, AccessPatternStats


class EventDrivenCollector:
    """Aggregates access events into cost-efficient behavior windows."""

    def aggregate_access_patterns(
        self,
        events: list[AccessEventRecord],
        as_of: datetime | None = None,
    ) -> dict[str, AccessPatternStats]:
        """Aggregate read/write behavior for 30d and 90d windows.

        Deduplication is performed by `event_id` to avoid double counting.
        """
        as_of = as_of or datetime.now(UTC)
        thirty_days = 30
        ninety_days = 90

        stats_by_object: dict[str, AccessPatternStats] = {}
        seen_event_ids: set[str] = set()

        for event in events:
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)

            days_ago = (as_of - event.timestamp).days
            if days_ago < 0 or days_ago > ninety_days:
                continue

            stats = stats_by_object.setdefault(event.object_id, AccessPatternStats())
            is_read = event.operation in {AccessOperation.READ, AccessOperation.LIST}
            is_write = event.operation == AccessOperation.WRITE

            if is_read:
                stats.read_count_90d += 1
                stats.read_bytes_90d += max(0, event.bytes_transferred)
                if stats.last_read_at is None or event.timestamp > stats.last_read_at:
                    stats.last_read_at = event.timestamp
            elif is_write:
                stats.write_count_90d += 1
                stats.write_bytes_90d += max(0, event.bytes_transferred)
                if stats.last_write_at is None or event.timestamp > stats.last_write_at:
                    stats.last_write_at = event.timestamp

            if days_ago < thirty_days:
                day_idx = thirty_days - days_ago - 1
                if is_read:
                    stats.read_count_30d += 1
                    stats.daily_reads_30d[day_idx] += 1
                elif is_write:
                    stats.write_count_30d += 1
                    stats.daily_writes_30d[day_idx] += 1

        return stats_by_object
