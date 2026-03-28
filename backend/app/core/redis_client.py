"""Redis Sentinel 기반 비동기 클라이언트.

Sentinel HA 구성에서 master 노드를 자동 탐색하며,
모든 I/O 는 asyncio 이벤트 루프에서 논블로킹으로 실행됩니다.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from redis.asyncio.sentinel import Sentinel

from app.config import settings

logger = logging.getLogger(__name__)

_sentinel: Sentinel | None = None
_redis: Any = None  # redis.asyncio.client.Redis
_lock = asyncio.Lock()


async def _get_sentinel() -> Sentinel:
    """Sentinel 객체 싱글턴 반환."""
    global _sentinel
    if _sentinel is None:
        _sentinel = Sentinel(
            settings.sentinel_hosts,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
    return _sentinel


async def get_redis() -> Any:
    """Redis master 커넥션 싱글턴 반환."""
    global _redis
    if _redis is None:
        async with _lock:
            if _redis is None:  # double-checked locking
                sentinel = await _get_sentinel()
                _redis = sentinel.master_for(
                    settings.REDIS_SENTINEL_MASTER,
                    socket_timeout=0.5,
                    decode_responses=True,
                )
                logger.info(
                    "Redis Sentinel master connection initialised",
                    extra={"master": settings.REDIS_SENTINEL_MASTER},
                )
    return _redis


async def redis_ping() -> bool:
    """헬스체크용 PING."""
    try:
        r = await get_redis()
        return await r.ping()
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False


# ── 기본 Key-Value 연산 ────────────────────────────────────────────────────────

async def redis_get(key: str) -> str | None:
    r = await get_redis()
    return await r.get(key)


async def redis_set(key: str, value: str, ex: int | None = None) -> None:
    r = await get_redis()
    await r.set(key, value, ex=ex)


async def redis_setex(key: str, ex: int, value: str) -> None:
    """SETEX 명령 – TTL(초) 을 명시적으로 지정."""
    r = await get_redis()
    await r.setex(key, ex, value)


async def redis_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def redis_exists(key: str) -> bool:
    r = await get_redis()
    return bool(await r.exists(key))


async def redis_ttl(key: str) -> int:
    """남은 TTL(초) 반환. 키 없으면 -2, TTL 없으면 -1."""
    r = await get_redis()
    return await r.ttl(key)


async def redis_incr(key: str) -> int:
    r = await get_redis()
    return await r.incr(key)


async def redis_incr_float(key: str, amount: float, ex: int | None = None) -> float:
    """INCRBYFLOAT – 키에 float 값을 더합니다. ex(초) 옵션으로 TTL 설정 가능."""
    r = await get_redis()
    result = await r.incrbyfloat(key, amount)
    if ex is not None:
        await r.expire(key, ex)
    return float(result)


# ── 분산 락 ───────────────────────────────────────────────────────────────────

async def redis_set_nx(key: str, value: str, ex: int) -> bool:
    """SET NX EX – 분산 락 획득. 성공 시 True 반환.

    Args:
        key:   락 키 (예: ``lock:strategy:42``)
        value: 락 소유자 식별자 (UUID 등)
        ex:    자동 해제 TTL (초)
    """
    r = await get_redis()
    result = await r.set(key, value, nx=True, ex=ex)
    return result is True


async def redis_del_if_equal(key: str, value: str) -> bool:
    """값이 일치할 때만 키 삭제 (Lua 스크립트, 원자적)."""
    lua_script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """
    r = await get_redis()
    result = await r.eval(lua_script, 1, key, value)
    return bool(result)


# ── Pub/Sub ───────────────────────────────────────────────────────────────────

async def redis_publish(channel: str, message: str) -> int:
    """채널에 메시지 발행. 수신자 수 반환."""
    r = await get_redis()
    return await r.publish(channel, message)


# ── Hash ──────────────────────────────────────────────────────────────────────

async def redis_hset(key: str, mapping: dict[str, str]) -> None:
    r = await get_redis()
    await r.hset(key, mapping=mapping)


async def redis_hget(key: str, field: str) -> str | None:
    r = await get_redis()
    return await r.hget(key, field)


async def redis_hgetall(key: str) -> dict[str, str]:
    r = await get_redis()
    return await r.hgetall(key)


# ── List (Queue) ──────────────────────────────────────────────────────────────

async def redis_lpush(key: str, *values: str) -> int:
    r = await get_redis()
    return await r.lpush(key, *values)


async def redis_rpop(key: str) -> str | None:
    r = await get_redis()
    return await r.rpop(key)
