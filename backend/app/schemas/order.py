"""주문 관련 Pydantic 스키마."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class OrderResponse(BaseModel):
    id: UUID
    strategy_id: UUID | None
    symbol: str
    side: str
    order_type: str
    price: Decimal | None
    quantity: Decimal
    filled_quantity: Decimal
    avg_fill_price: Decimal | None
    fee: Decimal
    status: str
    created_at: datetime
    filled_at: datetime | None

    model_config = {"from_attributes": True}
