"""백테스트 엔진.

과거 OHLCV 데이터를 순회하며 전략 조건을 시뮬레이션하고
성과 지표를 계산합니다.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.trading.strategy_evaluator import StrategyEvaluator

logger = logging.getLogger(__name__)

# 슬라이딩 윈도우 최소 캔들 수 (지표 계산용)
MIN_CANDLES = 50


@dataclass
class TradeRecord:
    """백테스트 단일 거래 기록."""

    entry_time: datetime
    exit_time: datetime | None
    side: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0


@dataclass
class BacktestMetrics:
    """백테스트 성과 지표."""

    initial_capital: float
    final_capital: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_holding_hours: float
    trades: list[dict] = field(default_factory=list)


class BacktestEngine:
    """이벤트 기반 백테스트 시뮬레이터.

    Args:
        condition_tree:  전략 조건 트리 dict (``entry`` / ``exit`` 키)
        order_config:    주문 설정 dict
        initial_capital: 초기 자본 (USDT)
        commission_pct:  거래당 수수료율 (예: 0.001 = 0.1%)
        slippage_pct:    슬리피지율 (예: 0.0005 = 0.05%)
    """

    def __init__(
        self,
        condition_tree: dict,
        order_config: dict,
        initial_capital: float = 10_000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.0005,
    ) -> None:
        self.condition_tree = condition_tree
        self.order_config = order_config
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.evaluator = StrategyEvaluator()

    def run(self, ohlcv_df: pd.DataFrame) -> BacktestMetrics:
        """전체 백테스트를 실행합니다.

        Args:
            ohlcv_df: columns=[open, high, low, close, volume], DatetimeIndex

        Returns:
            BacktestMetrics
        """
        if len(ohlcv_df) < MIN_CANDLES:
            raise ValueError(
                f"Not enough candles: {len(ohlcv_df)} < {MIN_CANDLES}"
            )

        capital = self.initial_capital
        position_qty: float = 0.0
        position_entry_price: float = 0.0
        position_entry_time: datetime | None = None

        trades: list[TradeRecord] = []
        equity_curve: list[float] = []

        entry_tree = self.condition_tree.get("entry", {})
        exit_tree = self.condition_tree.get("exit", {})
        qty_type = self.order_config.get("quantity_type", "balance_ratio")
        qty_value = float(self.order_config.get("quantity_value", 0.1))

        for i in range(MIN_CANDLES, len(ohlcv_df)):
            window = ohlcv_df.iloc[:i]
            row = ohlcv_df.iloc[i]
            current_price = float(row["close"])
            ts: datetime = ohlcv_df.index[i].to_pydatetime()

            # 현재 자본 = 현금 + 포지션 평가금액
            equity = capital + position_qty * current_price
            equity_curve.append(equity)

            if position_qty > 0 and exit_tree:
                exit_result = self.evaluator.evaluate(exit_tree, window)
                if exit_result.matched:
                    # 청산
                    exit_price = current_price * (1 - self.slippage_pct)
                    revenue = exit_price * position_qty
                    commission = revenue * self.commission_pct
                    cost_basis = position_entry_price * position_qty * (
                        1 + self.commission_pct
                    )
                    pnl = revenue - commission - cost_basis
                    pnl_pct = pnl / cost_basis * 100 if cost_basis > 0 else 0

                    holding_hours = (
                        (ts - position_entry_time).total_seconds() / 3600
                        if position_entry_time
                        else 0
                    )
                    trades.append(
                        TradeRecord(
                            entry_time=position_entry_time or ts,
                            exit_time=ts,
                            side="sell",
                            entry_price=position_entry_price,
                            exit_price=exit_price,
                            quantity=position_qty,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            commission=commission,
                        )
                    )
                    capital += revenue - commission
                    position_qty = 0.0
                    position_entry_price = 0.0
                    position_entry_time = None

            elif position_qty == 0 and entry_tree:
                entry_result = self.evaluator.evaluate(entry_tree, window)
                if entry_result.matched:
                    # 진입
                    entry_price = current_price * (1 + self.slippage_pct)
                    qty = self._calc_qty(qty_type, qty_value, entry_price, capital)
                    cost = entry_price * qty
                    commission = cost * self.commission_pct
                    if cost + commission <= capital and qty > 0:
                        capital -= cost + commission
                        position_qty = qty
                        position_entry_price = entry_price
                        position_entry_time = ts

        # 미청산 포지션 강제 청산 (마지막 캔들 종가)
        if position_qty > 0:
            last_price = float(ohlcv_df["close"].iloc[-1])
            exit_price = last_price * (1 - self.slippage_pct)
            revenue = exit_price * position_qty
            commission = revenue * self.commission_pct
            cost_basis = position_entry_price * position_qty * (1 + self.commission_pct)
            pnl = revenue - commission - cost_basis
            pnl_pct = pnl / cost_basis * 100 if cost_basis > 0 else 0
            trades.append(
                TradeRecord(
                    entry_time=position_entry_time or ohlcv_df.index[-1].to_pydatetime(),
                    exit_time=ohlcv_df.index[-1].to_pydatetime(),
                    side="sell",
                    entry_price=position_entry_price,
                    exit_price=exit_price,
                    quantity=position_qty,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    commission=commission,
                )
            )
            capital += revenue - commission

        final_capital = capital
        return self._compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            equity_curve=equity_curve,
            trades=trades,
        )

    # ── 지표 계산 ─────────────────────────────────────────────────────────────

    def _compute_metrics(
        self,
        initial_capital: float,
        final_capital: float,
        equity_curve: list[float],
        trades: list[TradeRecord],
    ) -> BacktestMetrics:
        total_return_pct = (
            (final_capital - initial_capital) / initial_capital * 100
            if initial_capital > 0
            else 0.0
        )

        # Max Drawdown
        max_drawdown_pct = 0.0
        if equity_curve:
            arr = np.array(equity_curve, dtype=float)
            peak = np.maximum.accumulate(arr)
            drawdown = (arr - peak) / np.where(peak > 0, peak, 1) * 100
            max_drawdown_pct = float(abs(drawdown.min()))

        # Sharpe / Sortino (일별 수익률 기준)
        sharpe = 0.0
        sortino = 0.0
        if len(equity_curve) > 1:
            returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
            mean_r = returns.mean()
            std_r = returns.std()
            if std_r > 0:
                sharpe = float(mean_r / std_r * math.sqrt(252))
            neg_returns = returns[returns < 0]
            if len(neg_returns) > 0:
                downside_std = neg_returns.std()
                if downside_std > 0:
                    sortino = float(mean_r / downside_std * math.sqrt(252))

        # Win rate & Profit factor
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        win_rate = len(winning) / len(trades) * 100 if trades else 0.0
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Avg holding hours
        holding_hours = [
            (t.exit_time - t.entry_time).total_seconds() / 3600
            for t in trades
            if t.exit_time
        ]
        avg_holding = sum(holding_hours) / len(holding_hours) if holding_hours else 0.0

        trades_detail = [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": round(t.pnl, 8),
                "pnl_pct": round(t.pnl_pct, 4),
                "commission": round(t.commission, 8),
            }
            for t in trades
        ]

        return BacktestMetrics(
            initial_capital=initial_capital,
            final_capital=round(final_capital, 8),
            total_return_pct=round(total_return_pct, 4),
            max_drawdown_pct=round(max_drawdown_pct, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 4),
            total_trades=len(trades),
            avg_holding_hours=round(avg_holding, 2),
            trades=trades_detail,
        )

    def _calc_qty(
        self,
        qty_type: str,
        qty_value: float,
        price: float,
        available: float,
    ) -> float:
        if price <= 0:
            return 0.0
        if qty_type == "fixed_amount":
            return qty_value / price
        if qty_type == "balance_ratio":
            ratio = min(max(qty_value, 0.0), 1.0)
            return (available * ratio) / price
        if qty_type == "fixed_quantity":
            return qty_value
        return 0.0
