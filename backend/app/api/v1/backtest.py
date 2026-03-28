"""백테스트 API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.backtest import BacktestResponse, BacktestRunRequest, BacktestTaskResponse
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtest", tags=["backtest"])
_svc = BacktestService()


@router.post("", response_model=BacktestTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_backtest(
    req: BacktestRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> BacktestTaskResponse:
    """백테스트를 Celery 태스크로 제출합니다."""
    record = await _svc.create_backtest(db, req, current_user.id)
    await db.commit()

    # Celery 태스크 제출
    try:
        from app.tasks.trading_tasks import run_backtest_task
        task = run_backtest_task.delay(str(record.id))
        task_id = task.id

        # celery task id 업데이트
        record.celery_task_id = task_id
        await db.commit()
    except Exception:
        task_id = "celery-unavailable"

    return BacktestTaskResponse(
        task_id=task_id,
        backtest_id=record.id,
    )


@router.get("", response_model=list[BacktestResponse])
async def list_backtests(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    strategy_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, le=100),
) -> list[BacktestResponse]:
    records = await _svc.list_backtests(db, current_user.id, strategy_id, limit)
    return [BacktestResponse.model_validate(r) for r in records]


@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> BacktestResponse:
    record = await _svc.get_backtest(db, backtest_id, current_user.id)
    return BacktestResponse.model_validate(record)
