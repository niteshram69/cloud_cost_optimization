"""Redis client configuration and utilities."""

import redis.asyncio as redis

from app.core.config import settings

# Global Redis client instance
_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
