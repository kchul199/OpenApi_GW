"""포트폴리오 / 잔고 API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.balance import Balance
from app.models.exchange_account import ExchangeAccount
from app.models.order import Order
from app.models.user import User

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """사용자 포트폴리오 요약 – 연결된 거래소 계정 및 잔고를 반환합니다."""
    accounts_result = await db.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.user_id == current_user.id,
            ExchangeAccount.is_active == True,
        )
    )
    accounts = accounts_result.scalars().all()

    summary: list[dict] = []
    total_usdt_value = 0.0

    for account in accounts:
        balances_result = await db.execute(
            select(Balance).where(Balance.exchange_account_id == account.id)
        )
        balances = balances_result.scalars().all()
        account_usdt = sum(float(b.usd_value or 0) for b in balances)
        total_usdt_value += account_usdt

        summary.append({
            "account_id": str(account.id),
            "exchange_id": account.exchange_id,
            "label": account.label,
            "is_testnet": account.is_testnet,
            "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
            "total_usdt_value": round(account_usdt, 2),
            "balances": [
                {
                    "currency": b.currency,
                    "free": float(b.free),
                    "locked": float(b.locked),
                    "total": float(b.total),
                    "usd_value": float(b.usd_value or 0),
                }
                for b in balances
                if float(b.total) > 0
            ],
        })

    return {
        "total_usdt_value": round(total_usdt_value, 2),
        "accounts": summary,
    }


@router.get("/pnl")
async def pnl_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """실현 손익 요약."""
    orders_result = await db.execute(
        select(Order).where(
            Order.user_id == current_user.id,
            Order.realized_pnl != None,
        )
    )
    orders = orders_result.scalars().all()

    total_pnl = sum(float(o.realized_pnl or 0) for o in orders)
    winning = [o for o in orders if float(o.realized_pnl or 0) > 0]
    losing = [o for o in orders if float(o.realized_pnl or 0) < 0]

    return {
        "total_realized_pnl": round(total_pnl, 8),
        "total_trades": len(orders),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(len(winning) / len(orders) * 100, 2) if orders else 0.0,
    }
