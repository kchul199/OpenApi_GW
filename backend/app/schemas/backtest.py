"""백테스트 관련 Pydantic 스키마."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class BacktestRunRequest(BaseModel):
    strategy_id: UUID
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("10000")
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005


class BacktestResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    total_return_pct: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    win_rate: float | None
    total_trades: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestTaskResponse(BaseModel):
    task_id: str
    backtest_id: UUID
    message: str = "Backtest submitted"
