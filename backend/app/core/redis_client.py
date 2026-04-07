from functools import lru_cache

import redis

from backend.app.core.config import settings


@lru_cache
def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
