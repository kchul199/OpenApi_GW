"""전략 서비스 – 전략 CRUD 및 활성화/일시정지 처리."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.redis_client import redis_delete, redis_set
from app.models.emergency_stop import EmergencyStop
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyCreate, StrategyUpdate

_AI_MODE_MAP = {"off": 0, "advisory": 1, "auto": 2}


class StrategyService:

    async def list_strategies(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> list[Strategy]:
        result = await db.execute(
            select(Strategy)
            .where(Strategy.user_id == user_id)
            .order_by(Strategy.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_strategy(
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> Strategy:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        if strategy is None:
            raise NotFoundException(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise ForbiddenException()
        return strategy

    async def create_strategy(
        self, db: AsyncSession, data: StrategyCreate, user_id: uuid.UUID
    ) -> Strategy:
        # hold_retry_interval, hold_max_retry 는 order_config 에 병합 저장
        order_config = dict(data.order_config)
        order_config.setdefault("hold_retry_interval", data.hold_retry_interval)
        order_config.setdefault("hold_max_retry", data.hold_max_retry)

        strategy = Strategy(
            id=uuid.uuid4(),
            user_id=user_id,
            name=data.name,
            symbol=data.symbol,
            timeframe=data.timeframe,
            condition_tree=data.condition_tree,
            order_config=order_config,
            ai_mode=_AI_MODE_MAP.get(data.ai_mode, 0),
            priority=data.priority,
        )
        db.add(strategy)
        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def update_strategy(
        self,
        db: AsyncSession,
        strategy_id: uuid.UUID,
        data: StrategyUpdate,
        user_id: uuid.UUID,
    ) -> Strategy:
        strategy = await self.get_strategy(db, strategy_id, user_id)

        if data.name is not None:
            strategy.name = data.name
        if data.condition_tree is not None:
            strategy.condition_tree = data.condition_tree
        if data.order_config is not None:
            strategy.order_config = data.order_config
        if data.ai_mode is not None:
            strategy.ai_mode = _AI_MODE_MAP.get(data.ai_mode, strategy.ai_mode)
        if data.priority is not None:
            strategy.priority = data.priority

        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def delete_strategy(
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        strategy = await self.get_strategy(db, strategy_id, user_id)
        await db.delete(strategy)
        await db.flush()

    async def activate_strategy(
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> Strategy:
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.is_active = True
        strategy.is_paused = False
        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def pause_strategy(
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> Strategy:
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.is_paused = True
        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def emergency_stop(
        self,
        db: AsyncSession,
        strategy_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str = "manual",
        detail: str | None = None,
    ) -> Strategy:
        """전략 긴급 정지 – Redis 플래그 + DB 이력 저장."""
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.is_active = False
        strategy.emergency_stopped = True

        # Redis 플래그 설정
        await redis_set(f"emergency:stop:{strategy_id}", "1", ex=86400 * 7)

        # EmergencyStop 이력 저장
        record = EmergencyStop(
            id=uuid.uuid4(),
            strategy_id=strategy_id,
            triggered_by_user_id=user_id,
            trigger_reason=reason,
            detail=detail,
            position_action="close_all",
            is_resumed=False,
        )
        db.add(record)

        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def resume_strategy(
        self,
        db: AsyncSession,
        strategy_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Strategy:
        """긴급 정지 해제 – 최근 EmergencyStop 레코드도 업데이트."""
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.emergency_stopped = False
        strategy.is_active = True
        strategy.is_paused = False

        await redis_delete(f"emergency:stop:{strategy_id}")

        # 가장 최근 미재개 EmergencyStop 레코드 업데이트
        es_result = await db.execute(
            select(EmergencyStop)
            .where(
                EmergencyStop.strategy_id == strategy_id,
                EmergencyStop.is_resumed == False,
            )
            .order_by(EmergencyStop.triggered_at.desc())
            .limit(1)
        )
        es = es_result.scalar_one_or_none()
        if es:
            es.is_resumed = True
            es.resumed_at = datetime.now(timezone.utc)
            es.resumed_by_user_id = user_id

        await db.flush()
        await db.refresh(strategy)
        return strategy
