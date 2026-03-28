"""대시보드 요약 API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.order import Order
from app.models.strategy import Strategy
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """대시보드 핵심 통계를 반환합니다."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 활성 전략 수
    strat_result = await db.execute(
        select(func.count(Strategy.id)).where(
            Strategy.user_id == current_user.id,
            Strategy.is_active == True,
        )
    )
    active_strategies = strat_result.scalar_one() or 0

    # 오늘 주문 수
    order_count_result = await db.execute(
        select(func.count(Order.id)).where(
            Order.user_id == current_user.id,
            Order.created_at >= today_start,
        )
    )
    trades_today = order_count_result.scalar_one() or 0

    # 오늘 실현 손익
    pnl_result = await db.execute(
        select(func.sum(Order.realized_pnl)).where(
            Order.user_id == current_user.id,
            Order.created_at >= today_start,
            Order.realized_pnl.isnot(None),
        )
    )
    profit_today = float(pnl_result.scalar_one() or 0)

    return {
        "active_strategies": active_strategies,
        "trades_today": trades_today,
        "profit_today": round(profit_today, 8),
        "profit_today_pct": 0.0,  # TODO: 초기 자본 대비 계산
    }


@router.get("/recent-orders")
async def recent_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """최근 10개 주문을 반환합니다."""
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    orders = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "symbol": o.symbol,
            "side": o.side,
            "order_type": o.order_type,
            "quantity": float(o.quantity),
            "average_fill_price": float(o.average_fill_price) if o.average_fill_price else None,
            "status": o.status,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]


@router.get("/market-prices")
async def market_prices(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """주요 암호화폐 현재가를 반환합니다."""
    from app.config import settings
    from app.exchange.ccxt_adapter import CcxtAdapter

    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    adapter = CcxtAdapter(
        exchange_id=settings.EXCHANGE_ID,
        api_key="",
        api_secret="",
        testnet=settings.use_testnet,
    )

    prices: list[dict] = []
    try:
        for symbol in symbols:
            try:
                ticker = await adapter.fetch_ticker(symbol)
                prices.append({
                    "symbol": symbol,
                    "price": ticker.get("last") or ticker.get("close", 0),
                    "change_24h": round(ticker.get("percentage", 0), 2),
                })
            except Exception:
                pass
    finally:
        await adapter.close()

    return prices
