"""전략 관리 API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.strategy import StrategyCreate, StrategyResponse, StrategyUpdate
from app.services.strategy_service import StrategyService

router = APIRouter(prefix="/strategies", tags=["strategies"])
_svc = StrategyService()


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> list[StrategyResponse]:
    strategies = await _svc.list_strategies(db, current_user.id)
    return [StrategyResponse.model_validate(s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: StrategyCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.create_strategy(db, data, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.get_strategy(db, strategy_id, current_user.id)
    return StrategyResponse.model_validate(strategy)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: uuid.UUID,
    data: StrategyUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.update_strategy(db, strategy_id, data, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await _svc.delete_strategy(db, strategy_id, current_user.id)
    await db.commit()


@router.post("/{strategy_id}/activate", response_model=StrategyResponse)
async def activate_strategy(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.activate_strategy(db, strategy_id, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)


@router.post("/{strategy_id}/pause", response_model=StrategyResponse)
async def pause_strategy(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.pause_strategy(db, strategy_id, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)


@router.post("/{strategy_id}/emergency-stop", response_model=StrategyResponse)
async def emergency_stop(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.emergency_stop(db, strategy_id, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)


@router.post("/{strategy_id}/resume", response_model=StrategyResponse)
async def resume_strategy(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    strategy = await _svc.resume_strategy(db, strategy_id, current_user.id)
    await db.commit()
    return StrategyResponse.model_validate(strategy)
