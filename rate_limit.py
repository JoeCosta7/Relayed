from redis_client import r
import os
from database import Customer, TIER_LIMITS
from datetime import datetime, timezone


lua_script = """local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
local new_tokens = math.min(capacity, tokens + elapsed * refill_rate)

if new_tokens >= 1 then
    new_tokens = new_tokens - 1
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return {1, 0}
else
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    local retry_after = math.ceil((1 - new_tokens) / refill_rate)
    return {0, retry_after}
end"""

def check_rate_limit(customer: Customer) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    capacity, refill_rate = TIER_LIMITS[customer.tier]
    key = f"ratelimit:{customer.id}"
    now = datetime.now(timezone.utc).timestamp()
    result = r.eval(lua_script, 1, key, capacity, refill_rate, now)
    allowed, retry_after = result
    return bool(allowed), int(retry_after)

    
