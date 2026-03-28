"""유지보수 Celery 태스크 – 잔고 동기화, 만료 토큰 정리 등."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.maintenance_tasks.sync_all_balances")
def sync_all_balances() -> dict:
    """활성 거래소 계정의 잔고를 동기화합니다."""
    async def _execute():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.exchange.ccxt_adapter import CcxtAdapter
        from app.core.security import decrypt_api_key
        from app.models.exchange_account import ExchangeAccount
        from app.models.balance import Balance

        synced = 0
        errors = 0

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ExchangeAccount).where(ExchangeAccount.is_active == True)
            )
            accounts = result.scalars().all()

            for account in accounts:
                try:
                    api_key = decrypt_api_key(account.api_key_encrypted)
                    api_secret = decrypt_api_key(account.api_secret_encrypted)

                    adapter = CcxtAdapter(
                        exchange_id=account.exchange_id,
                        api_key=api_key,
                        api_secret=api_secret,
                        testnet=account.is_testnet,
                    )
                    raw_balance = await adapter.fetch_balance()
                    await adapter.close()

                    now = datetime.now(timezone.utc)
                    for currency, amounts in raw_balance.get("total", {}).items():
                        if not amounts:
                            continue
                        total = float(amounts)
                        if total <= 0:
                            continue
                        free = float(raw_balance.get("free", {}).get(currency) or 0)
                        locked = float(raw_balance.get("used", {}).get(currency) or 0)

                        bal_result = await db.execute(
                            select(Balance).where(
                                Balance.exchange_account_id == account.id,
                                Balance.currency == currency,
                            )
                        )
                        bal = bal_result.scalar_one_or_none()
                        if bal is None:
                            bal = Balance(
                                exchange_account_id=account.id,
                                currency=currency,
                            )
                            db.add(bal)

                        bal.free = free
                        bal.locked = locked
                        bal.total = total
                        bal.synced_at = now

                    account.last_synced_at = now
                    synced += 1

                except Exception as exc:
                    logger.error("Balance sync failed for account %s: %s", account.id, exc)
                    errors += 1

            await db.commit()

        return {"synced": synced, "errors": errors}

    return _run_async(_execute())


@celery_app.task(name="app.tasks.maintenance_tasks.cleanup_expired_tokens")
def cleanup_expired_tokens() -> dict:
    """만료된 JWT 블랙리스트 항목을 DB 에서 삭제합니다."""
    async def _execute():
        from sqlalchemy import delete
        from app.database import AsyncSessionLocal
        from app.models.jwt_blacklist import JWTBlacklist

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(JWTBlacklist).where(JWTBlacklist.expires_at < now)
            )
            deleted = result.rowcount
            await db.commit()

        logger.info("Cleaned up %d expired JWT tokens", deleted)
        return {"deleted": deleted}

    return _run_async(_execute())


@celery_app.task(name="app.tasks.maintenance_tasks.send_daily_report")
def send_daily_report() -> dict:
    """일일 거래 리포트를 사용자에게 전송합니다."""
    async def _execute():
        from sqlalchemy import select, func
        from app.database import AsyncSessionLocal
        from app.models.order import Order

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    func.count(Order.id).label("total"),
                    func.sum(Order.realized_pnl).label("total_pnl"),
                ).where(
                    Order.created_at >= today_start,
                    Order.status == "closed",
                )
            )
            row = result.one()

        total_trades = row.total or 0
        total_pnl = float(row.total_pnl or 0)

        logger.info(
            "Daily report: trades=%d total_pnl=%.2f USDT",
            total_trades,
            total_pnl,
        )

        pnl_sign = "+" if total_pnl >= 0 else ""
        report_text = (
            f"📊 <b>CoinTrader 일일 리포트</b>\n"
            f"날짜: {now.strftime('%Y-%m-%d')}\n"
            f"거래 횟수: {total_trades}건\n"
            f"실현 손익: {pnl_sign}{total_pnl:.2f} USDT"
        )
        from app.services.notification_service import NotificationService
        svc = NotificationService()
        await svc.notify(report_text, subject="CoinTrader 일일 리포트")

        return {"trades": total_trades, "total_pnl": total_pnl}

    return _run_async(_execute())
