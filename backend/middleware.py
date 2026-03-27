"""
Rate limiting middleware using a Redis-backed token bucket algorithm.

All tunables are sourced from config.settings.
"""

import time
from fastapi import HTTPException, Request
from redis_config import redis_client
from config import settings

# Lua script for atomic Token Bucket
# KEYS[1] = bucket key
# ARGV[1] = capacity
# ARGV[2] = refill_rate (tokens/sec)
# ARGV[3] = now (unix timestamp)
TOKEN_BUCKET_LUA = """
local bucket = redis.call('HMGET', KEYS[1], 'last_refill', 'tokens')
local last_refill = tonumber(bucket[1]) or tonumber(ARGV[3])
local tokens = tonumber(bucket[2]) or tonumber(ARGV[1])

local elapsed = math.max(0, ARGV[3] - last_refill)
local refill = elapsed * ARGV[2]
tokens = math.min(tonumber(ARGV[1]), tokens + refill)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', KEYS[1], 'last_refill', ARGV[3], 'tokens', tokens)
    return 1
else
    return 0
end
"""


async def rate_limiter(request: Request) -> bool:
    """FastAPI dependency that enforces per-IP rate limiting."""
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"

    allowed = await redis_client.eval(
        TOKEN_BUCKET_LUA,
        1,
        key,
        settings.rate_limit_capacity,
        settings.rate_limit_refill_rate,
        time.time(),
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too Many Requests — slow down.",
        )

    return True
