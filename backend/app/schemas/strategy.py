"""전략 관련 Pydantic 스키마."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

_AI_MODE_INT_TO_STR: dict[int, str] = {0: "off", 1: "advisory", 2: "auto"}
_AI_MODE_STR_TO_INT: dict[str, int] = {"off": 0, "advisory": 1, "auto": 2}


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

    @field_validator("ai_mode")
    @classmethod
    def validate_ai_mode(cls, v: str) -> str:
        if v not in _AI_MODE_STR_TO_INT:
            raise ValueError(f"ai_mode must be one of {list(_AI_MODE_STR_TO_INT)}")
        return v


class StrategyUpdate(BaseModel):
    name: str | None = None
    condition_tree: dict | None = None
    order_config: dict | None = None
    ai_mode: str | None = None
    priority: int | None = None

    @field_validator("ai_mode")
    @classmethod
    def validate_ai_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in _AI_MODE_STR_TO_INT:
            raise ValueError(f"ai_mode must be one of {list(_AI_MODE_STR_TO_INT)}")
        return v


class StrategyResponse(BaseModel):
    id: UUID
    name: str
    symbol: str
    timeframe: str
    condition_tree: dict
    order_config: dict
    ai_mode: str          # 항상 "off" | "advisory" | "auto" 로 반환
    priority: int
    is_active: bool
    is_paused: bool
    emergency_stopped: bool
    total_trades: int
    total_pnl: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_ai_mode(cls, data: object) -> object:
        """DB에서 int(0/1/2)로 저장된 ai_mode를 str로 변환."""
        if hasattr(data, "__dict__"):
            # ORM 객체인 경우
            raw = getattr(data, "ai_mode", None)
            if isinstance(raw, int):
                object.__setattr__(data, "ai_mode", _AI_MODE_INT_TO_STR.get(raw, "off"))
        elif isinstance(data, dict):
            raw = data.get("ai_mode")
            if isinstance(raw, int):
                data["ai_mode"] = _AI_MODE_INT_TO_STR.get(raw, "off")
        return data
