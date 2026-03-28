"""주문 실행기.

CcxtAdapter 를 통해 실제 거래소에 주문을 제출하고,
Order 레코드를 DB 에 기록합니다.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange.ccxt_adapter import CcxtAdapter
from app.models.order import Order
from app.trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class OrderExecutor:
    """거래소 주문 생성 및 DB 기록을 담당하는 실행기."""

    def __init__(self, adapter: CcxtAdapter, risk_manager: RiskManager) -> None:
        self.adapter = adapter
        self.risk_manager = risk_manager

    async def execute_buy(
        self,
        db: AsyncSession,
        *,
        strategy_id: uuid.UUID,
        user_id: uuid.UUID,
        symbol: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        trigger_source: str = "signal",
    ) -> Order:
        """매수 주문을 실행하고 Order 레코드를 반환합니다.

        Args:
            db:             DB 세션
            strategy_id:    전략 UUID
            user_id:        사용자 UUID
            symbol:         거래 심볼 (예: BTC/USDT)
            order_type:     주문 유형 (market / limit / stop)
            quantity:       주문 수량
            price:          주문 가격 (limit 주문 시 필수)
            trigger_source: 주문 트리거 출처
        """
        return await self._execute(
            db,
            strategy_id=strategy_id,
            user_id=user_id,
            symbol=symbol,
            side="buy",
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_source=trigger_source,
        )

    async def execute_sell(
        self,
        db: AsyncSession,
        *,
        strategy_id: uuid.UUID,
        user_id: uuid.UUID,
        symbol: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        trigger_source: str = "signal",
    ) -> Order:
        """매도 주문을 실행하고 Order 레코드를 반환합니다."""
        return await self._execute(
            db,
            strategy_id=strategy_id,
            user_id=user_id,
            symbol=symbol,
            side="sell",
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_source=trigger_source,
        )

    async def _execute(
        self,
        db: AsyncSession,
        *,
        strategy_id: uuid.UUID,
        user_id: uuid.UUID,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None,
        trigger_source: str,
    ) -> Order:
        """공통 주문 실행 로직."""
        logger.info(
            "Executing %s %s %s qty=%.8f price=%s trigger=%s",
            side,
            order_type,
            symbol,
            quantity,
            price,
            trigger_source,
        )

        raw: dict = {}
        status = "open"
        exchange_order_id: str | None = None
        filled_quantity: float = 0.0
        average_fill_price: float | None = None
        fee: float = 0.0
        fee_currency: str | None = None

        try:
            raw = await self.adapter.create_order(
                symbol=symbol,
                order_type=order_type,
                side=side,
                amount=quantity,
                price=price,
            )
            exchange_order_id = raw.get("id")
            status = raw.get("status", "open")
            filled_quantity = float(raw.get("filled") or 0)
            average_fill_price = raw.get("average") or raw.get("price")
            if average_fill_price is not None:
                average_fill_price = float(average_fill_price)
            fee_info = raw.get("fee") or {}
            fee = float(fee_info.get("cost") or 0)
            fee_currency = fee_info.get("currency")
        except Exception as exc:
            logger.error("Exchange order failed: %s", exc)
            status = "rejected"
            raw = {"error": str(exc)}

        order = Order(
            id=uuid.uuid4(),
            strategy_id=strategy_id,
            user_id=user_id,
            exchange_id=self.adapter.exchange_id,
            exchange_order_id=exchange_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            filled_quantity=filled_quantity,
            average_fill_price=average_fill_price,
            fee=fee,
            fee_currency=fee_currency,
            status=status,
            trigger_source=trigger_source,
            raw_response=json.dumps(raw),
        )

        db.add(order)
        await db.flush()
        logger.info("Order saved id=%s status=%s", order.id, order.status)
        return order

    async def cancel(
        self, db: AsyncSession, order: Order
    ) -> Order:
        """미체결 주문을 취소합니다."""
        if not order.exchange_order_id:
            logger.warning("No exchange_order_id – skipping cancel for %s", order.id)
            return order

        try:
            raw = await self.adapter.cancel_order(
                order.exchange_order_id, order.symbol
            )
            order.status = "canceled"
            order.raw_response = json.dumps(raw)
        except Exception as exc:
            logger.error("Cancel order failed: %s", exc)

        await db.flush()
        return order
