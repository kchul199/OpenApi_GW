"""트레이딩 엔진.

활성화된 전략을 순회하며 조건을 평가하고 주문을 실행합니다.
Celery 태스크에서 주기적으로 호출됩니다.

ai_mode:
    0 (off)       – AI 자문 없이 신호 즉시 실행
    1 (advisory)  – AI 자문 요청 후 recommendation == "execute" 일 때만 실행
    2 (auto)      – AI 자문 없이 신호 즉시 실행 (advisory와 달리 항상 실행)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExchangeException, TradingHaltedException
from app.exchange.ccxt_adapter import CcxtAdapter
from app.models.order import Order
from app.models.strategy import Strategy
from app.trading.executor import OrderExecutor
from app.trading.risk_manager import RiskManager
from app.trading.strategy_evaluator import StrategyEvaluator

logger = logging.getLogger(__name__)

# ai_mode int 값
_AI_OFF = 0
_AI_ADVISORY = 1
_AI_AUTO = 2


class TradingEngine:
    """전략 평가 → AI 자문(선택) → 리스크 검사 → 주문 실행 파이프라인.

    Args:
        adapter: CcxtAdapter 인스턴스 (이미 초기화된 거래소 클라이언트)
        db:      비동기 DB 세션
    """

    def __init__(self, adapter: CcxtAdapter, db: AsyncSession) -> None:
        self.adapter = adapter
        self.db = db
        self.risk_manager = RiskManager()
        self.evaluator = StrategyEvaluator()
        self.executor = OrderExecutor(adapter, self.risk_manager)

    # ── 진입점 ────────────────────────────────────────────────────────────────

    async def run_once(self, strategy_id: uuid.UUID) -> dict:
        """단일 전략에 대해 한 번의 평가·실행 사이클을 수행합니다."""
        result: dict = {
            "strategy_id": str(strategy_id),
            "signal": None,
            "order_id": None,
            "skipped_reason": None,
            "ai_recommendation": None,
        }

        # 1. 전략 조회
        strategy = await self._load_strategy(strategy_id)
        if strategy is None:
            result["skipped_reason"] = "strategy_not_found"
            return result

        if not strategy.is_active or strategy.is_paused:
            result["skipped_reason"] = "strategy_inactive_or_paused"
            return result

        # 2. 리스크 검사 (긴급 정지 플래그)
        try:
            await self.risk_manager.can_trade(str(strategy.id), str(strategy.user_id))
        except TradingHaltedException as e:
            result["skipped_reason"] = str(e)
            return result

        # 3. OHLCV 데이터 조회
        try:
            raw_ohlcv = await self.adapter.fetch_ohlcv(
                strategy.symbol, strategy.timeframe, limit=200
            )
        except ExchangeException as e:
            logger.error("fetch_ohlcv error strategy=%s: %s", strategy_id, e)
            result["skipped_reason"] = f"exchange_error: {e}"
            return result

        ohlcv_df = self._to_dataframe(raw_ohlcv)
        if ohlcv_df.empty:
            result["skipped_reason"] = "empty_ohlcv"
            return result

        current_price = float(ohlcv_df["close"].iloc[-1])

        # 4. 조건 트리 평가
        condition_tree: dict = strategy.condition_tree or {}
        entry_tree = condition_tree.get("entry", {})
        exit_tree = condition_tree.get("exit", {})

        entry_result = self.evaluator.evaluate(entry_tree, ohlcv_df) if entry_tree else None
        exit_result = self.evaluator.evaluate(exit_tree, ohlcv_df) if exit_tree else None

        # 5. 현재 포지션 파악
        open_qty = await self._open_position(strategy.id)

        # 6. 신호 감지
        order_config: dict = strategy.order_config or {}
        signal: str | None = None
        triggered_conditions: list[str] = []

        if exit_result and exit_result.matched and open_qty > 0:
            signal = "sell"
            triggered_conditions = exit_result.triggered
        elif entry_result and entry_result.matched and open_qty == 0:
            signal = "buy"
            triggered_conditions = entry_result.triggered

        if signal is None:
            return result

        result["signal"] = signal

        # 7. AI 자문 (advisory 모드)
        ai_mode: int = strategy.ai_mode if isinstance(strategy.ai_mode, int) else _AI_OFF
        if ai_mode == _AI_ADVISORY:
            ai_result = await self._consult_ai(
                strategy=strategy,
                signal=signal,
                triggered_conditions=triggered_conditions,
                current_price=current_price,
                ohlcv_df=ohlcv_df,
            )
            result["ai_recommendation"] = ai_result.get("recommendation")
            if ai_result.get("recommendation") != "execute":
                result["skipped_reason"] = (
                    f"ai_advisory: {ai_result.get('recommendation')} "
                    f"(confidence={ai_result.get('confidence', 0):.2f})"
                )
                return result

        # 8. 리스크 한도 검사 (매수 신호에만 적용)
        order: Order | None = None

        if signal == "sell":
            order = await self.executor.execute_sell(
                self.db,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                symbol=strategy.symbol,
                order_type=order_config.get("order_type", "market"),
                quantity=open_qty,
                price=current_price if order_config.get("order_type") == "limit" else None,
                trigger_source="signal" if ai_mode == _AI_OFF else "ai_advisory",
            )
        else:  # buy
            balance_info = await self.adapter.fetch_balance()
            available_usdt = float(balance_info.get("free", {}).get("USDT", 0))
            max_pos = float(order_config.get("max_position_usdt", available_usdt))
            daily_limit = float(order_config.get("daily_limit_usdt", max_pos))
            today_traded = await self._today_traded(strategy.id)

            if not self.risk_manager.check_position_limit(0, max_pos):
                result["skipped_reason"] = "position_limit"
                return result
            if not self.risk_manager.check_daily_limit(today_traded, daily_limit):
                result["skipped_reason"] = "daily_limit"
                return result

            qty = self.risk_manager.calculate_quantity(
                quantity_type=order_config.get("quantity_type", "balance_ratio"),
                quantity_value=float(order_config.get("quantity_value", 0.1)),
                price=current_price,
                available_balance=available_usdt,
            )
            if qty <= 0:
                result["skipped_reason"] = "zero_quantity"
                return result

            order = await self.executor.execute_buy(
                self.db,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                symbol=strategy.symbol,
                order_type=order_config.get("order_type", "market"),
                quantity=qty,
                price=current_price if order_config.get("order_type") == "limit" else None,
                trigger_source="signal" if ai_mode == _AI_OFF else "ai_advisory",
            )

        if order:
            result["order_id"] = str(order.id)
            await self.db.commit()
            traded_usdt = float(order.quantity) * current_price
            await self._increment_today_traded(strategy.id, traded_usdt)

        return result

    # ── AI 자문 ───────────────────────────────────────────────────────────────

    async def _consult_ai(
        self,
        strategy: Strategy,
        signal: str,
        triggered_conditions: list[str],
        current_price: float,
        ohlcv_df: pd.DataFrame,
    ) -> dict:
        """AIService 를 통해 Claude API 자문을 요청합니다."""
        try:
            from app.services.ai_service import AIService

            # 최근 5개 캔들을 시장 맥락으로 전달
            recent = ohlcv_df.tail(5)[["open", "high", "low", "close", "volume"]]
            market_context = recent.to_dict(orient="records")

            svc = AIService()
            return await svc.consult(
                self.db,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                symbol=strategy.symbol,
                timeframe=strategy.timeframe,
                signal=signal,
                triggered_conditions=triggered_conditions,
                current_price=current_price,
                market_context={"recent_candles": market_context},
            )
        except Exception as exc:
            logger.warning("AI consult failed, defaulting to execute: %s", exc)
            # AI 자문 실패 시 advisory 모드에서는 신중하게 hold
            return {"recommendation": "hold", "confidence": 0.0, "reasoning": str(exc)}

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────

    async def _load_strategy(self, strategy_id: uuid.UUID) -> Strategy | None:
        result = await self.db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        return result.scalar_one_or_none()

    async def _open_position(self, strategy_id: uuid.UUID) -> float:
        """전략의 현재 보유 수량 합계를 반환합니다."""
        buy_result = await self.db.execute(
            select(Order).where(
                Order.strategy_id == strategy_id,
                Order.side == "buy",
                Order.status.in_(["closed", "partially_filled"]),
            )
        )
        sell_result = await self.db.execute(
            select(Order).where(
                Order.strategy_id == strategy_id,
                Order.side == "sell",
                Order.status.in_(["closed", "partially_filled"]),
            )
        )
        buys = buy_result.scalars().all()
        sells = sell_result.scalars().all()
        buy_qty = sum(float(o.filled_quantity) for o in buys)
        sell_qty = sum(float(o.filled_quantity) for o in sells)
        return max(buy_qty - sell_qty, 0.0)

    async def _today_traded(self, strategy_id: uuid.UUID) -> float:
        from app.core.redis_client import redis_get
        key = f"daily_traded:{strategy_id}:{datetime.now(timezone.utc).date()}"
        val = await redis_get(key)
        return float(val) if val else 0.0

    async def _increment_today_traded(self, strategy_id: uuid.UUID, amount: float) -> None:
        from app.core.redis_client import redis_incr_float
        key = f"daily_traded:{strategy_id}:{datetime.now(timezone.utc).date()}"
        await redis_incr_float(key, amount, ex=86400)

    @staticmethod
    def _to_dataframe(raw: list) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.set_index("timestamp").sort_index().astype(float)
