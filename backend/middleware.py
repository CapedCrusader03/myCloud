import time
import asyncio
from fastapi import HTTPException, Request, Depends
from redis_config import redis_client

# Lua script for atomic Token Bucket
# KEYS[1] = bucket key
# ARGV[1] = capacity
# ARGV[2] = refill_rate (tokens/sec)
# ARGV[3] = now
token_bucket_lua = """
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

async def rate_limiter(request: Request):
    # Simple IP-based key
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"
    
    # Defaults: 10 burst tokens, refills at 2 tokens per second
    capacity = 10
    refill_rate = 2
    now = time.time()
    
    # Execute the Lua script atomically
    allowed = await redis_client.eval(token_bucket_lua, 1, key, capacity, refill_rate, now)
    
    if not allowed:
        raise HTTPException(status_code=429, detail="Too Many Requests - Slow down!")
    
    return True
