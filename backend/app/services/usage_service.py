import hashlib
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.redis_client import get_redis_client
from backend.app.models import BillingCycle, BillingCycleStatus, UsageAggregate, UsageBucket, UsageEvent, User
from backend.app.services.public_data_guard import is_public_dataset_user


class UsageService:
    def __init__(self, db: Session):
        self.db = db

    def track_request(
        self,
        *,
        user_id: int,
        api_key_id: int | None,
        endpoint: str,
        method: str,
        data_volume_bytes: int = 0,
        compute_units: int = 0,
        idempotency_key: str | None = None,
    ) -> bool:
        user = self.db.scalar(select(User).where(User.id == user_id))
        if user and is_public_dataset_user(user):
            return False

        now = datetime.now(UTC)
        request_hash = self._request_hash(
            user_id=user_id,
            api_key_id=api_key_id,
            endpoint=endpoint,
            method=method,
            idempotency_key=idempotency_key,
            occurred_at=now,
        )
        if idempotency_key:
            existing = self.db.scalar(
                select(UsageEvent.id).where(
                    UsageEvent.user_id == user_id,
                    UsageEvent.api_key_id == api_key_id,
                    UsageEvent.endpoint == endpoint,
                    UsageEvent.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return False

        event = UsageEvent(
            user_id=user_id,
            api_key_id=api_key_id,
            endpoint=endpoint,
            method=method,
            request_count=1,
            data_volume_bytes=max(0, data_volume_bytes),
            compute_units=max(0, compute_units),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            occurred_at=now,
        )
        self.db.add(event)
        self._increment_open_billing_cycle(
            user_id=user_id,
            request_count=1,
        )
        self.db.commit()

        redis_client = self._safe_redis()
        if not redis_client:
            self._upsert_db_aggregate(
                user_id=user_id,
                api_key_id=api_key_id,
                endpoint=endpoint,
                bucket_start=self._hour_floor(now),
                request_count=1,
                data_volume_bytes=data_volume_bytes,
                compute_units=compute_units,
            )
            self.db.commit()
            return True

        bucket = self._hour_floor(now).isoformat()
        endpoint_fingerprint = hashlib.sha1(endpoint.encode("utf-8")).hexdigest()[:16]
        key = f"usage:h:{bucket}:{user_id}:{api_key_id or 0}:{endpoint_fingerprint}"
        try:
            pipe = redis_client.pipeline()
            if idempotency_key:
                idempotency_redis_key = (
                    f"usage:idempotency:{user_id}:{api_key_id or 0}:{endpoint}:{idempotency_key}"
                )
                if not redis_client.set(idempotency_redis_key, "1", nx=True, ex=settings.usage_redis_ttl_seconds):
                    return False
            pipe.hincrby(key, "request_count", 1)
            pipe.hincrby(key, "data_volume_bytes", max(0, data_volume_bytes))
            pipe.hincrby(key, "compute_units", max(0, compute_units))
            pipe.hset(key, "endpoint", endpoint)
            pipe.hset(key, "bucket_start", bucket)
            pipe.expire(key, settings.usage_redis_ttl_seconds)
            pipe.sadd("usage:pending_keys", key)
            pipe.execute()
        except RedisError:
            self._upsert_db_aggregate(
                user_id=user_id,
                api_key_id=api_key_id,
                endpoint=endpoint,
                bucket_start=self._hour_floor(now),
                request_count=1,
                data_volume_bytes=data_volume_bytes,
                compute_units=compute_units,
            )
            self.db.commit()
        return True

    def flush_redis_aggregates(self) -> int:
        redis_client = self._safe_redis()
        if not redis_client:
            return 0

        try:
            keys = list(redis_client.smembers("usage:pending_keys"))
        except RedisError:
            return 0

        flushed = 0
        for key in keys[: settings.usage_flush_batch_size]:
            try:
                payload = redis_client.hgetall(key)
            except RedisError:
                continue
            if not payload:
                redis_client.srem("usage:pending_keys", key)
                continue

            parts = key.split(":")
            if len(parts) < 7:
                redis_client.srem("usage:pending_keys", key)
                continue

            try:
                user_id = int(parts[4])
                api_key_id = int(parts[5]) or None
                bucket_start = datetime.fromisoformat(payload.get("bucket_start", ""))
                endpoint = payload["endpoint"]
                request_count = int(payload.get("request_count", "0"))
                data_volume_bytes = int(payload.get("data_volume_bytes", "0"))
                compute_units = int(payload.get("compute_units", "0"))
            except (TypeError, ValueError, KeyError):
                redis_client.srem("usage:pending_keys", key)
                continue

            self._upsert_db_aggregate(
                user_id=user_id,
                api_key_id=api_key_id,
                endpoint=endpoint,
                bucket_start=bucket_start,
                request_count=request_count,
                data_volume_bytes=data_volume_bytes,
                compute_units=compute_units,
            )
            redis_client.delete(key)
            redis_client.srem("usage:pending_keys", key)
            flushed += 1

        if flushed:
            self.db.commit()
        return flushed

    def current_cycle_usage(self, *, user_id: int, cycle_start: datetime, cycle_end: datetime) -> int:
        summed = self.db.scalar(
            select(func.sum(UsageEvent.request_count)).where(
                UsageEvent.user_id == user_id,
                UsageEvent.occurred_at >= cycle_start,
                UsageEvent.occurred_at < cycle_end,
            )
        )
        return int(summed or 0)

    def _upsert_db_aggregate(
        self,
        *,
        user_id: int,
        api_key_id: int | None,
        endpoint: str,
        bucket_start: datetime,
        request_count: int,
        data_volume_bytes: int,
        compute_units: int,
    ) -> None:
        current = self.db.scalar(
            select(UsageAggregate).where(
                UsageAggregate.user_id == user_id,
                UsageAggregate.api_key_id == api_key_id,
                UsageAggregate.endpoint == endpoint,
                UsageAggregate.bucket == UsageBucket.HOUR,
                UsageAggregate.bucket_start == bucket_start,
            )
        )
        if not current:
            current = UsageAggregate(
                user_id=user_id,
                api_key_id=api_key_id,
                endpoint=endpoint,
                bucket=UsageBucket.HOUR,
                bucket_start=bucket_start,
                request_count=0,
                data_volume_bytes=0,
                compute_units=0,
            )
            self.db.add(current)

        current.request_count += max(0, request_count)
        current.data_volume_bytes += max(0, data_volume_bytes)
        current.compute_units += max(0, compute_units)

    def _increment_open_billing_cycle(self, *, user_id: int, request_count: int) -> None:
        now = datetime.now(UTC)
        cycle = self.db.scalar(
            select(BillingCycle).where(
                BillingCycle.user_id == user_id,
                BillingCycle.status == BillingCycleStatus.OPEN,
                BillingCycle.starts_at <= now,
                BillingCycle.ends_at > now,
            )
        )
        if cycle:
            cycle.request_count += max(0, request_count)

    def _safe_redis(self) -> Redis | None:
        try:
            client = get_redis_client()
            client.ping()
            return client
        except Exception:
            return None

    def _hour_floor(self, dt: datetime) -> datetime:
        return dt.replace(minute=0, second=0, microsecond=0)

    def _request_hash(
        self,
        *,
        user_id: int,
        api_key_id: int | None,
        endpoint: str,
        method: str,
        idempotency_key: str | None,
        occurred_at: datetime,
    ) -> str:
        material = f"{user_id}:{api_key_id}:{endpoint}:{method}:{idempotency_key or ''}:{occurred_at.isoformat()}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
