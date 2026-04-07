"""Safe cross-cloud migration engine with dry-run and rollback support."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import time
from dataclasses import asdict, dataclass

from app.migration_engine.audit import MigrationAuditLogger
from app.migration_engine.gateways import GatewayFactory, ObjectReference


@dataclass(slots=True)
class MigrationRequest:
    """Migration request for a single object."""

    tenant_id: str
    object_id: str
    source: ObjectReference
    target: ObjectReference
    target_tier: str
    dry_run: bool = True
    delete_source_after_copy: bool = False


@dataclass(slots=True)
class MigrationResult:
    """Outcome of a migration attempt."""

    status: str
    message: str
    source_checksum: str | None = None
    target_checksum: str | None = None
    rollback_performed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class MigrationEngine:
    """Executes throttled and auditable migrations."""

    def __init__(
        self,
        gateway_factory: GatewayFactory,
        audit_logger: MigrationAuditLogger,
        max_parallel: int = 4,
        max_ops_per_second: float = 4.0,
    ):
        self._factory = gateway_factory
        self._audit = audit_logger
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._max_ops_per_second = max_ops_per_second
        self._last_operation = 0.0
        self._throttle_lock = asyncio.Lock()

    async def migrate(self, request: MigrationRequest) -> MigrationResult:
        """Migrate one object with checksum verification and rollback."""
        async with self._semaphore:
            await self._throttle()

            if request.dry_run:
                await self._audit.record(
                    tenant_id=request.tenant_id,
                    object_id=request.object_id,
                    source=request.source.uri,
                    target=request.target.uri,
                    status="dry_run",
                    detail="No data copied; generated migration plan only",
                )
                return MigrationResult(
                    status="dry_run",
                    message="Migration plan generated (dry-run)",
                )

            source_gateway = self._factory.get_gateway(request.source.provider)
            target_gateway = self._factory.get_gateway(request.target.provider)

            source_checksum: str | None = None
            target_checksum: str | None = None
            uploaded = False
            tmp_path = ""

            try:
                source_head = await source_gateway.head(request.source)
                source_checksum = source_head.checksum

                with tempfile.NamedTemporaryFile(prefix="migration_", delete=False) as tmp_file:
                    tmp_path = tmp_file.name

                await source_gateway.download(request.source, tmp_path)
                if not source_checksum:
                    source_checksum = await asyncio.to_thread(self._sha256_file, tmp_path)

                await target_gateway.upload(tmp_path, request.target, storage_tier=request.target_tier)
                uploaded = True

                target_head = await target_gateway.head(request.target)
                target_checksum = target_head.checksum
                if not target_checksum:
                    target_checksum = await asyncio.to_thread(self._sha256_file, tmp_path)

                if source_checksum and target_checksum and source_checksum != target_checksum:
                    await self._rollback(
                        target_gateway=target_gateway,
                        request=request,
                        reason="checksum mismatch",
                    )
                    return MigrationResult(
                        status="failed",
                        message="Checksum validation failed after copy",
                        source_checksum=source_checksum,
                        target_checksum=target_checksum,
                        rollback_performed=True,
                    )

                if request.delete_source_after_copy:
                    await source_gateway.delete(request.source)

                await self._audit.record(
                    tenant_id=request.tenant_id,
                    object_id=request.object_id,
                    source=request.source.uri,
                    target=request.target.uri,
                    status="success",
                    detail="Object migrated successfully",
                )
                return MigrationResult(
                    status="success",
                    message="Object migrated successfully",
                    source_checksum=source_checksum,
                    target_checksum=target_checksum,
                )
            except Exception as exc:
                if uploaded:
                    await self._rollback(
                        target_gateway=target_gateway,
                        request=request,
                        reason=f"failure during migration: {exc}",
                    )
                await self._audit.record(
                    tenant_id=request.tenant_id,
                    object_id=request.object_id,
                    source=request.source.uri,
                    target=request.target.uri,
                    status="failed",
                    detail=str(exc),
                )
                return MigrationResult(
                    status="failed",
                    message=str(exc),
                    source_checksum=source_checksum,
                    target_checksum=target_checksum,
                    rollback_performed=uploaded,
                )
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

    async def _rollback(self, target_gateway, request: MigrationRequest, reason: str) -> None:
        await target_gateway.delete(request.target)
        await self._audit.record(
            tenant_id=request.tenant_id,
            object_id=request.object_id,
            source=request.source.uri,
            target=request.target.uri,
            status="rollback",
            detail=reason,
        )

    async def _throttle(self) -> None:
        if self._max_ops_per_second <= 0:
            return

        min_interval = 1.0 / self._max_ops_per_second
        async with self._throttle_lock:
            now = time.monotonic()
            wait_for = min_interval - (now - self._last_operation)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_operation = time.monotonic()

    @staticmethod
    def _sha256_file(path: str) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()
