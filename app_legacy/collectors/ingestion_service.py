"""Collector orchestration service.

Combines inventory exports and event/log streams to build object usage snapshots
with minimal cloud control-plane calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.collectors.event_driven import EventDrivenCollector
from app.collectors.models import AccessEventRecord, AccessPatternStats, InventoryObjectRecord, ObjectUsageSnapshot


class MetadataIngestionService:
    """Builds object snapshots from batch inventory and event-driven activity."""

    def __init__(self, event_collector: EventDrivenCollector | None = None):
        self._event_collector = event_collector or EventDrivenCollector()

    def build_snapshots(
        self,
        inventory_records: list[InventoryObjectRecord],
        access_events: list[AccessEventRecord],
        as_of: datetime | None = None,
    ) -> list[ObjectUsageSnapshot]:
        """Join inventory and access events into point-in-time object snapshots."""
        as_of = as_of or datetime.now(UTC)
        patterns = self._event_collector.aggregate_access_patterns(access_events, as_of)

        snapshots: list[ObjectUsageSnapshot] = []
        for inventory in inventory_records:
            pattern = patterns.get(inventory.object_id, AccessPatternStats())
            snapshots.append(ObjectUsageSnapshot(inventory=inventory, access=pattern))

        return snapshots
