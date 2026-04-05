"""
Global Redis client initialized at application startup.
"""

from __future__ import annotations

from collections.abc import Awaitable
import logging
from typing import cast

from redis.asyncio import Redis, from_url
from redis.asyncio.cluster import RedisCluster

from gateway.config import settings

logger = logging.getLogger(__name__)

# Global Redis client instance
RedisClient = Redis | RedisCluster
redis_client: RedisClient | None = None


async def init_redis() -> None:
    """Initialize the global Redis connection pool."""
    global redis_client
    if redis_client is None:
        logger.info(
            f"Connecting to Redis at {settings.redis.url} (Cluster mode: {settings.redis.cluster_mode})"
        )
        if settings.redis.cluster_mode:
            redis_client = RedisCluster.from_url(
                settings.redis.url,
                max_connections=settings.redis.max_connections,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                decode_responses=True,
            )
        else:
            redis_client = from_url(
                settings.redis.url,
                max_connections=settings.redis.max_connections,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                decode_responses=True,
            )
        # Verify connection
        try:
            await cast(Awaitable[object], redis_client.ping())
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise


async def close_redis() -> None:
    """Close the global Redis connection pool."""
    global redis_client
    if redis_client:
        await cast(Awaitable[object], redis_client.aclose())
        logger.info("Redis connection closed")
        redis_client = None


def get_redis() -> RedisClient:
    """Returns the initialized Redis client. Raises error if not initialized."""
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client
