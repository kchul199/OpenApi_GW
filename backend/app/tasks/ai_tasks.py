"""AI 자문 Celery 태스크."""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.ai_tasks.request_ai_consultation",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    time_limit=30,
)
def request_ai_consultation(
    self,
    strategy_id: str,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    signal: str,
    triggered_conditions: list[str],
    current_price: float,
    market_context: dict,
) -> dict:
    """AI 자문 요청 태스크."""
    async def _execute():
        from app.database import AsyncSessionLocal
        from app.services.ai_service import AIService

        svc = AIService()
        async with AsyncSessionLocal() as db:
            result = await svc.consult(
                db,
                strategy_id=uuid.UUID(strategy_id),
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                signal=signal,
                triggered_conditions=triggered_conditions,
                current_price=current_price,
                market_context=market_context,
            )
            await db.commit()
            return result

    try:
        return _run_async(_execute())
    except Exception as exc:
        logger.error("AI consultation task failed: %s", exc)
        raise self.retry(exc=exc)
