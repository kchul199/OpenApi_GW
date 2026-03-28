"""백테스트 서비스 – 백테스트 생성 및 결과 조회."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.backtest_result import BacktestResult
from app.models.strategy import Strategy
from app.schemas.backtest import BacktestRunRequest


class BacktestService:

    async def create_backtest(
        self,
        db: AsyncSession,
        req: BacktestRunRequest,
        user_id: uuid.UUID,
    ) -> BacktestResult:
        """백테스트 레코드를 pending 상태로 생성합니다."""
        # 전략 소유권 확인
        strat_result = await db.execute(
            select(Strategy).where(
                Strategy.id == req.strategy_id,
                Strategy.user_id == user_id,
            )
        )
        if strat_result.scalar_one_or_none() is None:
            raise NotFoundException(f"Strategy {req.strategy_id} not found")

        record = BacktestResult(
            id=uuid.uuid4(),
            strategy_id=req.strategy_id,
            user_id=user_id,
            start_date=datetime.combine(req.start_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            ),
            end_date=datetime.combine(req.end_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            ),
            initial_capital=float(req.initial_capital),
            commission_pct=req.commission_pct,
            slippage_pct=req.slippage_pct,
            status="pending",
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        return record

    async def get_backtest(
        self,
        db: AsyncSession,
        backtest_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BacktestResult:
        result = await db.execute(
            select(BacktestResult).where(BacktestResult.id == backtest_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundException(f"Backtest {backtest_id} not found")
        if record.user_id != user_id:
            raise ForbiddenException()
        return record

    async def list_backtests(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        strategy_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[BacktestResult]:
        query = select(BacktestResult).where(BacktestResult.user_id == user_id)
        if strategy_id:
            query = query.where(BacktestResult.strategy_id == strategy_id)
        query = query.order_by(BacktestResult.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_result(
        self,
        db: AsyncSession,
        backtest_id: uuid.UUID,
        metrics: dict,
        status: str = "completed",
        error_message: str | None = None,
    ) -> BacktestResult:
        result = await db.execute(
            select(BacktestResult).where(BacktestResult.id == backtest_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundException(f"Backtest {backtest_id} not found")

        record.status = status
        record.completed_at = datetime.now(timezone.utc)
        record.error_message = error_message

        if status == "completed":
            record.final_capital = metrics.get("final_capital")
            record.total_return_pct = metrics.get("total_return_pct")
            record.max_drawdown_pct = metrics.get("max_drawdown_pct")
            record.sharpe_ratio = metrics.get("sharpe_ratio")
            record.sortino_ratio = metrics.get("sortino_ratio")
            record.win_rate = metrics.get("win_rate")
            record.total_trades = metrics.get("total_trades")
            record.profit_factor = metrics.get("profit_factor")
            record.avg_holding_hours = metrics.get("avg_holding_hours")
            record.trades_detail = metrics.get("trades")

        await db.flush()
        await db.refresh(record)
        return record
