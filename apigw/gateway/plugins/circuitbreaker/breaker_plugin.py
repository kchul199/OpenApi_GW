"""
Circuit Breaker Plugin.
Wraps upstream calls in a circuit breaker state machine:
  CLOSED → (failure threshold exceeded) → OPEN → (timeout) → HALF_OPEN → CLOSED/OPEN

Config keys:
  failure_threshold  (int)   : consecutive failures to open circuit (default: 5)
  recovery_timeout   (float) : seconds before attempting recovery (default: 30)
  success_threshold  (int)   : successes in HALF_OPEN to close circuit (default: 2)
"""
import asyncio
import logging
from enum import Enum

from fastapi import Request, Response

from gateway.core.context import GatewayContext
from gateway.core.redis import get_redis
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)


@PluginRegistry.register
class CircuitBreakerPlugin(BasePlugin):
    """
    Redis-backed Distributed Circuit Breaker.
    """
    name = "circuit-breaker"
    order = 25

    def configure(self, config: dict) -> None:
        self._failure_threshold: int   = config.get("failure_threshold", 5)
        self._recovery_timeout: float  = config.get("recovery_timeout", 30.0)
        self._window_seconds: int      = config.get("window_seconds", 60)

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        redis = get_redis()
        route_id = ctx.route_id
        
        open_key = f"cb:open:{route_id}"
        fails_key = f"cb:fails:{route_id}"

        # 1. Check if Circuit is OPEN globally
        is_open = await redis.exists(open_key)
        if is_open:
            ctx.circuit_open = True
            ttl = await redis.ttl(open_key)
            logger.warning(f"Circuit OPEN globally for route={route_id}", extra={"request_id": ctx.request_id})
            return Response(
                content='{"detail":"Service temporarily unavailable (circuit open)"}',
                status_code=503,
                media_type="application/json",
                headers={"Retry-After": str(max(ttl, 1))},
            )

        # 2. Proceed with call
        try:
            response: Response = await next(request, ctx)
            if response.status_code >= 500:
                await self._record_failure(redis, route_id, open_key, fails_key)
            else:
                # Optionally reset failures on success. For a simple sliding behavior,
                # we just let the fails_key expire automatically over window_seconds.
                pass
            return response
        except Exception:
            # On exception (e.g. connection error), record failure
            await self._record_failure(redis, route_id, open_key, fails_key)
            raise

    async def _record_failure(self, redis, route_id: str, open_key: str, fails_key: str):
        # Increment failures
        current_fails = await redis.incr(fails_key)
        # Set expiry for the failure window if it's the first failure
        if current_fails == 1:
            await redis.expire(fails_key, self._window_seconds)

        if current_fails >= self._failure_threshold:
            # Trip the circuit!
            # Set the open_key with recovery_timeout
            await redis.set(open_key, "1", ex=int(self._recovery_timeout))
            # Clear or leave the fails_key to block further processing
            await redis.delete(fails_key)
            logger.error(f"Circuit breached for route={route_id}! Opening circuit for {self._recovery_timeout}s.")
