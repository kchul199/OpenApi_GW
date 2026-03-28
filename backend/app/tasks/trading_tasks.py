"""트레이딩 Celery 태스크."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """동기 Celery 컨텍스트에서 비동기 코루틴을 실행합니다."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.trading_tasks.run_strategy",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def run_strategy(self, strategy_id: str) -> dict:
    """단일 전략 실행 태스크."""
    async def _execute():
        from app.config import settings
        from app.database import AsyncSessionLocal
        from app.exchange.ccxt_adapter import CcxtAdapter
        from app.models.exchange_account import ExchangeAccount
        from app.core.security import decrypt_api_key
        from app.models.strategy import Strategy
        from app.trading.engine import TradingEngine

        async with AsyncSessionLocal() as db:
            # 전략 조회
            strat_result = await db.execute(
                select(Strategy).where(Strategy.id == uuid.UUID(strategy_id))
            )
            strategy = strat_result.scalar_one_or_none()
            if strategy is None:
                return {"skipped": "strategy_not_found"}

            # 거래소 계정 조회 (첫 번째 활성 계정 사용)
            acct_result = await db.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.user_id == strategy.user_id,
                    ExchangeAccount.is_active == True,
                )
            )
            account = acct_result.scalar_one_or_none()
            if account is None:
                return {"skipped": "no_exchange_account"}

            api_key = decrypt_api_key(account.api_key_encrypted)
            api_secret = decrypt_api_key(account.api_secret_encrypted)

            adapter = CcxtAdapter(
                exchange_id=account.exchange_id,
                api_key=api_key,
                api_secret=api_secret,
                testnet=account.is_testnet,
            )
            try:
                engine = TradingEngine(adapter=adapter, db=db)
                result = await engine.run_once(uuid.UUID(strategy_id))
                return result
            finally:
                await adapter.close()

    try:
        return _run_async(_execute())
    except Exception as exc:
        logger.error("run_strategy task failed for %s: %s", strategy_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.trading_tasks.run_all_active_strategies")
def run_all_active_strategies() -> dict:
    """활성화된 모든 전략을 실행합니다. 동일 사용자·동일 심볼 충돌 시 우선순위 기반 해결."""
    async def _execute():
        from app.database import AsyncSessionLocal
        from app.models.strategy import Strategy
        from app.services.conflict_service import ConflictService

        conflict_svc = ConflictService()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(
                    Strategy.is_active == True,
                    Strategy.is_paused == False,
                    Strategy.emergency_stopped == False,
                )
            )
            strategies = result.scalars().all()

        # 사용자별, 심볼별로 그룹화하여 충돌 전략 파악
        # 동일 사용자 + 동일 심볼에 활성 전략이 2개 이상이면 우선순위 높은 것만 실행
        from collections import defaultdict
        user_symbol_map: dict[tuple, list[Strategy]] = defaultdict(list)
        for s in strategies:
            user_symbol_map[(s.user_id, s.symbol)].append(s)

        eligible_ids: set[uuid.UUID] = set()
        conflict_groups: list[list[Strategy]] = []

        for group in user_symbol_map.values():
            if len(group) == 1:
                eligible_ids.add(group[0].id)
            else:
                # 충돌 가능 그룹: 우선순위 내림차순 정렬 후 최우선만 실행
                sorted_group = sorted(group, key=lambda s: s.priority, reverse=True)
                eligible_ids.add(sorted_group[0].id)
                if len(group) > 1:
                    conflict_groups.append(group)

        # 충돌 기록 (잠재적 충돌만 기록, 실제 신호 방향은 불명이므로 pending)
        async with AsyncSessionLocal() as db:
            for group in conflict_groups:
                from itertools import combinations as _combs
                for s_a, s_b in _combs(group, 2):
                    from app.models.strategy_conflict import StrategyConflict
                    winner = s_a if s_a.priority >= s_b.priority else s_b
                    record = StrategyConflict(
                        id=uuid.uuid4(),
                        strategy_a_id=s_a.id,
                        strategy_b_id=s_b.id,
                        symbol=s_a.symbol,
                        signal_a="unknown",
                        signal_b="unknown",
                        resolution="priority",
                        winner_strategy_id=winner.id,
                        notes=(
                            f"Potential conflict: same symbol {s_a.symbol}, "
                            f"resolved by priority ({s_a.priority} vs {s_b.priority})"
                        ),
                        detected_at=datetime.now(timezone.utc),
                        resolved_at=datetime.now(timezone.utc),
                    )
                    db.add(record)
            await db.commit()

        # 우선 전략만 실행
        for s in strategies:
            if s.id in eligible_ids:
                run_strategy.delay(str(s.id))

        return {
            "dispatched": len(eligible_ids),
            "skipped_conflicts": len(strategies) - len(eligible_ids),
        }

    return _run_async(_execute())


@celery_app.task(
    name="app.tasks.trading_tasks.run_backtest_task",
    bind=True,
    time_limit=3600,
)
def run_backtest_task(self, backtest_id: str) -> dict:
    """백테스트 실행 태스크."""
    async def _execute():
        import pandas as pd
        from app.database import AsyncSessionLocal
        from app.exchange.ccxt_adapter import CcxtAdapter
        from app.models.backtest_result import BacktestResult
        from app.models.exchange_account import ExchangeAccount
        from app.models.strategy import Strategy
        from app.core.security import decrypt_api_key
        from app.services.backtest_service import BacktestService
        from app.trading.backtest_engine import BacktestEngine

        svc = BacktestService()

        async with AsyncSessionLocal() as db:
            # 백테스트 레코드 로드
            bt_result = await db.execute(
                select(BacktestResult).where(
                    BacktestResult.id == uuid.UUID(backtest_id)
                )
            )
            bt = bt_result.scalar_one_or_none()
            if bt is None:
                return {"error": "backtest_not_found"}

            # 상태 running 으로 변경
            bt.status = "running"
            await db.commit()

            # 전략 조회
            strat_result = await db.execute(
                select(Strategy).where(Strategy.id == bt.strategy_id)
            )
            strategy = strat_result.scalar_one_or_none()
            if strategy is None:
                await svc.update_result(db, bt.id, {}, "failed", "Strategy not found")
                await db.commit()
                return {"error": "strategy_not_found"}

            # 거래소 계정 조회
            acct_result = await db.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.user_id == bt.user_id,
                    ExchangeAccount.is_active == True,
                )
            )
            account = acct_result.scalar_one_or_none()
            if account is None:
                await svc.update_result(db, bt.id, {}, "failed", "No exchange account")
                await db.commit()
                return {"error": "no_exchange_account"}

            api_key = decrypt_api_key(account.api_key_encrypted)
            api_secret = decrypt_api_key(account.api_secret_encrypted)

            try:
                adapter = CcxtAdapter(
                    exchange_id=account.exchange_id,
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=account.is_testnet,
                )

                # OHLCV 조회 (1000 캔들)
                raw_ohlcv = await adapter.fetch_ohlcv(
                    strategy.symbol, strategy.timeframe, limit=1000
                )
                await adapter.close()

                ohlcv_df = pd.DataFrame(
                    raw_ohlcv,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                ohlcv_df["timestamp"] = pd.to_datetime(
                    ohlcv_df["timestamp"], unit="ms", utc=True
                )
                ohlcv_df = ohlcv_df.set_index("timestamp").astype(float)

                # 날짜 필터
                ohlcv_df = ohlcv_df[
                    (ohlcv_df.index >= pd.Timestamp(bt.start_date))
                    & (ohlcv_df.index <= pd.Timestamp(bt.end_date))
                ]

                engine = BacktestEngine(
                    condition_tree=strategy.condition_tree,
                    order_config=strategy.order_config,
                    initial_capital=float(bt.initial_capital),
                    commission_pct=float(bt.commission_pct),
                    slippage_pct=float(bt.slippage_pct),
                )
                metrics = engine.run(ohlcv_df)

                await svc.update_result(
                    db,
                    bt.id,
                    {
                        "final_capital": metrics.final_capital,
                        "total_return_pct": metrics.total_return_pct,
                        "max_drawdown_pct": metrics.max_drawdown_pct,
                        "sharpe_ratio": metrics.sharpe_ratio,
                        "sortino_ratio": metrics.sortino_ratio,
                        "win_rate": metrics.win_rate,
                        "total_trades": metrics.total_trades,
                        "profit_factor": metrics.profit_factor,
                        "avg_holding_hours": metrics.avg_holding_hours,
                        "trades": metrics.trades,
                    },
                    "completed",
                )
                await db.commit()
                return {"status": "completed", "backtest_id": backtest_id}

            except Exception as exc:
                logger.error("Backtest failed: %s", exc)
                await svc.update_result(db, uuid.UUID(backtest_id), {}, "failed", str(exc))
                await db.commit()
                return {"error": str(exc)}

    return _run_async(_execute())
