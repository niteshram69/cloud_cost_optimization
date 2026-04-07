"""Domain models for metadata and access-pattern collection.

The collector layer intentionally operates only on metadata and access events.
No object body reads are performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AccessOperation(str, Enum):
    """Normalized object operations derived from cloud access logs/events."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"


@dataclass(slots=True)
class InventoryObjectRecord:
    """Object metadata from inventory reports or event feeds."""

    tenant_id: str
    provider: str
    region: str
    bucket: str
    object_key: str
    storage_tier: str
    size_bytes: int
    last_modified_at: datetime
    last_accessed_at: datetime | None = None
    etag: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def object_id(self) -> str:
        """Stable multi-cloud object identifier."""
        return f"{self.provider}://{self.bucket}/{self.object_key}"


@dataclass(slots=True)
class AccessEventRecord:
    """Single object access event from AWS/GCP/Azure event streams."""

    tenant_id: str
    provider: str
    region: str
    bucket: str
    object_key: str
    event_id: str
    operation: AccessOperation
    timestamp: datetime
    bytes_transferred: int = 0

    @property
    def object_id(self) -> str:
        """Stable multi-cloud object identifier."""
        return f"{self.provider}://{self.bucket}/{self.object_key}"


@dataclass(slots=True)
class AccessPatternStats:
    """Aggregated access pattern features over recent windows."""

    read_count_30d: int = 0
    write_count_30d: int = 0
    read_count_90d: int = 0
    write_count_90d: int = 0
    read_bytes_90d: int = 0
    write_bytes_90d: int = 0
    daily_reads_30d: list[int] = field(default_factory=lambda: [0] * 30)
    daily_writes_30d: list[int] = field(default_factory=lambda: [0] * 30)
    last_read_at: datetime | None = None
    last_write_at: datetime | None = None

    @property
    def read_write_ratio(self) -> float:
        """Read/write ratio with denominator guard for low-volume datasets."""
        return self.read_count_90d / (self.write_count_90d + 1)


@dataclass(slots=True)
class ObjectUsageSnapshot:
    """Merged inventory metadata and derived access behavior."""

    inventory: InventoryObjectRecord
    access: AccessPatternStats

    @property
    def tenant_id(self) -> str:
        return self.inventory.tenant_id

    @property
    def object_id(self) -> str:
        return self.inventory.object_id
