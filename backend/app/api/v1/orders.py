"""주문 조회 및 취소 API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.order import OrderResponse
from app.services.order_service import OrderService

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
    """미체결 주문을 취소합니다.

    거래소 API 연결이 필요하므로 실제 배포에서는 exchange_account 정보를
    주입해 CcxtAdapter 를 초기화해야 합니다.
    현재는 DB 상태만 canceled 로 변경합니다.
    """
    order = await _svc.get_order(db, order_id, current_user.id)
    if order.status not in ("open", "partially_filled"):
        return {"message": f"Order already in status '{order.status}'"}
    order.status = "canceled"
    await db.commit()
    return {"message": "Order cancel requested"}
