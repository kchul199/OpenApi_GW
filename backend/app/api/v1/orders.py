"""주문 조회 및 취소 API."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.security import decrypt_api_key
from app.database import get_db
from app.dependencies import get_current_user
from app.exchange.ccxt_adapter import CcxtAdapter
from app.models.exchange_account import ExchangeAccount
from app.models.user import User
from app.schemas.order import OrderResponse
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])
_svc = OrderService()


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    strategy_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> list[OrderResponse]:
    orders = await _svc.list_orders(
        db,
        user_id=current_user.id,
        strategy_id=strategy_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    order = await _svc.get_order(db, order_id, current_user.id)
    return OrderResponse.model_validate(order)


@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
async def cancel_order(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """미체결 주문을 취소합니다. 거래소 API를 통해 실제 취소 요청을 전송합니다."""
    order = await _svc.get_order(db, order_id, current_user.id)
    if order.status not in ("open", "partially_filled"):
        return {"message": f"Order already in status '{order.status}'"}

    # 거래소 API 취소 시도 (exchange_order_id 가 있는 경우)
    if order.exchange_order_id:
        acc_result = await db.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == current_user.id,
                ExchangeAccount.exchange_id == order.exchange_id,
                ExchangeAccount.is_active == True,
            ).limit(1)
        )
        account = acc_result.scalar_one_or_none()
        if account is None:
            raise BadRequestException(
                f"No active exchange account found for '{order.exchange_id}'"
            )
        adapter = CcxtAdapter(
            exchange_id=account.exchange_id,
            api_key=decrypt_api_key(account.api_key_encrypted),
            api_secret=decrypt_api_key(account.api_secret_encrypted),
            testnet=account.is_testnet,
        )
        try:
            await adapter.cancel_order(order.exchange_order_id, order.symbol)
        except Exception as exc:
            logger.warning("Exchange cancel_order failed: %s", exc)
            raise BadRequestException(f"Exchange cancel failed: {exc}") from exc
        finally:
            await adapter.close()

    order.status = "canceled"
    await db.commit()
    return {"message": "Order canceled successfully"}
