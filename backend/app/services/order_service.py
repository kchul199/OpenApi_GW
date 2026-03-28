"""주문 서비스 – 주문 목록 조회 및 취소."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.exchange.ccxt_adapter import CcxtAdapter
from app.models.order import Order
from app.trading.executor import OrderExecutor
from app.trading.risk_manager import RiskManager


class OrderService:

    async def list_orders(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        strategy_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        query = select(Order).where(Order.user_id == user_id)
        if strategy_id:
            query = query.where(Order.strategy_id == strategy_id)
        if status:
            query = query.where(Order.status == status)
        query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_order(
        self, db: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID
    ) -> Order:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundException(f"Order {order_id} not found")
        if order.user_id != user_id:
            raise ForbiddenException()
        return order

    async def cancel_order(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        adapter: CcxtAdapter,
    ) -> Order:
        order = await self.get_order(db, order_id, user_id)
        if order.status not in ("open", "partially_filled"):
            raise ValueError(f"Cannot cancel order in status '{order.status}'")

        executor = OrderExecutor(adapter, RiskManager())
        return await executor.cancel(db, order)
