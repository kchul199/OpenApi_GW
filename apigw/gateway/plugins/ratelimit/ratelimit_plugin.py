"""
Token Bucket Rate Limiter Plugin.
Supports per-IP, per-user, and per-API-key rate limiting.
Uses an in-process token bucket (no external dependency required).
For clustered deployments, swap with Redis Lua script backend.

Config keys:
  limit     (int)   : max requests per window
  window    (int)   : window size in seconds (default: 60)
  key_func  (str)   : "ip" | "user" | "api_key"  (default: ip)
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import Request, Response

from gateway.core.context import GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry
from gateway.core.redis import get_redis

logger = logging.getLogger(__name__)


# Lua script for token bucket rate limiting (atomic operation)
_LUA_SCRIPT = """
local key         = KEYS[1]
local capacity    = tonumber(ARGV[1])
local rate        = tonumber(ARGV[2])
local now         = tonumber(ARGV[3])
local requested   = 1

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
else
    local elapsed = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + elapsed * rate)
end

local allowed = 0
if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
end

redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
-- Expire slightly longer than it takes to completely refill
redis.call("EXPIRE", key, math.ceil(capacity / rate) + 2)

return allowed
"""

@PluginRegistry.register
class RateLimiterPlugin(BasePlugin):
    name = "rate-limiter"
    order = 20

    def configure(self, config: dict) -> None:
        self._limit: int     = config.get("limit", 100)
        self._window: int    = config.get("window", 60)
        self._key_func: str  = config.get("key_func", "ip")
        self._rate: float    = self._limit / self._window
        self._script_sha     = None

    async def _get_script_sha(self, redis_client) -> str:
        if self._script_sha is None:
            self._script_sha = await redis_client.script_load(_LUA_SCRIPT)
        return self._script_sha

    def _resolve_key(self, request: Request, ctx: GatewayContext) -> str:
        if self._key_func == "user":
            return f"ratelimit:user:{ctx.principal}" if ctx.principal else f"ratelimit:ip:{self._ip(request)}"
        if self._key_func == "api_key":
            return f"ratelimit:apikey:{ctx.principal}"
        return f"ratelimit:ip:{self._ip(request)}"

    @staticmethod
    def _ip(request: Request) -> str:
        xff = request.headers.get("x-forwarded-for", "")
        return xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        key = self._resolve_key(request, ctx)

        try:
            redis_client = get_redis()
            script_sha = await self._get_script_sha(redis_client)
            
            import time
            now = time.time()
            
            # call Redis EVALSHA
            allowed = await redis_client.evalsha(
                script_sha,
                1,              # numkeys
                key,            # KEYS[1]
                self._limit,    # ARGV[1] = capacity
                self._rate,     # ARGV[2] = rate (tokens/sec)
                now             # ARGV[3] = now
            )
            
            if not allowed:
                logger.warning(f"Rate limit exceeded", extra={"request_id": ctx.request_id, "limit_key": key})
                return Response(
                    content='{"detail":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                    headers={
                        "Retry-After": str(self._window),
                        "X-RateLimit-Limit": str(self._limit),
                    },
                )
        except Exception as exc:
            # If Redis fails, fail open (allow traffic) but log error
            logger.error(f"Redis rate limiter failed: {exc}", extra={"request_id": ctx.request_id})

        return await next(request, ctx)
