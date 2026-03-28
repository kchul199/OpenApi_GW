"""전략 서비스 – 전략 CRUD 및 활성화/일시정지 처리."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.redis_client import redis_delete, redis_set
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyCreate, StrategyUpdate


class StrategyService:

    async def list_strategies(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> list[Strategy]:
        result = await db.execute(
            select(Strategy).where(Strategy.user_id == user_id).order_by(
                Strategy.created_at.desc()
            )
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
        ai_mode_map = {"off": 0, "advisory": 1, "auto": 2}
        strategy = Strategy(
            id=uuid.uuid4(),
            user_id=user_id,
            name=data.name,
            symbol=data.symbol,
            timeframe=data.timeframe,
            condition_tree=data.condition_tree,
            order_config=data.order_config,
            ai_mode=ai_mode_map.get(data.ai_mode, 0),
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
        ai_mode_map = {"off": 0, "advisory": 1, "auto": 2}

        if data.name is not None:
            strategy.name = data.name
        if data.condition_tree is not None:
            strategy.condition_tree = data.condition_tree
        if data.order_config is not None:
            strategy.order_config = data.order_config
        if data.ai_mode is not None:
            strategy.ai_mode = ai_mode_map.get(data.ai_mode, strategy.ai_mode)
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
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> Strategy:
        """전략 긴급 정지 – Redis 플래그 설정 + DB 업데이트."""
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.is_active = False
        strategy.emergency_stopped = True
        await redis_set(f"emergency:stop:{strategy_id}", "1", ex=86400 * 7)
        await db.flush()
        await db.refresh(strategy)
        return strategy

    async def resume_strategy(
        self, db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
    ) -> Strategy:
        """긴급 정지 해제."""
        strategy = await self.get_strategy(db, strategy_id, user_id)
        strategy.emergency_stopped = False
        strategy.is_active = True
        strategy.is_paused = False
        await redis_delete(f"emergency:stop:{strategy_id}")
        await db.flush()
        await db.refresh(strategy)
        return strategy
