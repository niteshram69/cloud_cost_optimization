"""Audit logging for migration operations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class MigrationAuditEvent:
    """Immutable migration audit event."""

    timestamp: str
    tenant_id: str
    object_id: str
    source: str
    target: str
    status: str
    detail: str


class MigrationAuditLogger:
    """Appends migration events as JSON lines for traceability."""

    def __init__(self, log_path: str):
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def record(
        self,
        tenant_id: str,
        object_id: str,
        source: str,
        target: str,
        status: str,
        detail: str,
    ) -> None:
        event = MigrationAuditEvent(
            timestamp=datetime.now(UTC).isoformat(),
            tenant_id=tenant_id,
            object_id=object_id,
            source=source,
            target=target,
            status=status,
            detail=detail,
        )

        async with self._lock:
            await asyncio.to_thread(self._append_line, event)

    def _append_line(self, event: MigrationAuditEvent) -> None:
        line = json.dumps(asdict(event), separators=(",", ":"))
        with open(self._log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
