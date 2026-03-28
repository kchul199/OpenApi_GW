"""전략 관련 Pydantic 스키마."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StrategyCreate(BaseModel):
    name: str
    symbol: str
    timeframe: str
    condition_tree: dict
    order_config: dict
    ai_mode: str = "off"
    priority: int = 5
    hold_retry_interval: int = 300
    hold_max_retry: int = 3


class StrategyUpdate(BaseModel):
    name: str | None = None
    condition_tree: dict | None = None
    order_config: dict | None = None
    ai_mode: str | None = None
    priority: int | None = None


class StrategyResponse(BaseModel):
    id: UUID
    name: str
    symbol: str
    timeframe: str
    condition_tree: dict
    order_config: dict
    ai_mode: str
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
