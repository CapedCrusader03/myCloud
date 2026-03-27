"""
Redis client configuration.

Connection URL is sourced from config.settings.
"""

import redis.asyncio as redis
from config import settings

# Singleton-style Redis client
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis():
    """Dependency for providing a redis connection."""
    return redis_client
