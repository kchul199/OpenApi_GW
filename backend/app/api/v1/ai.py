"""AI 자문 조회 API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.ai_consultation import AIConsultation
from app.models.strategy import Strategy
from app.models.user import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/advice")
async def list_advice(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    strategy_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """AI 자문 목록을 반환합니다."""
    # 현재 사용자의 전략 ID 목록 조회
    strat_ids_result = await db.execute(
        select(Strategy.id).where(Strategy.user_id == current_user.id)
    )
    user_strategy_ids = {row[0] for row in strat_ids_result.all()}

    query = select(AIConsultation).where(
        AIConsultation.strategy_id.in_(user_strategy_ids)
    )
    if strategy_id:
        query = query.where(AIConsultation.strategy_id == strategy_id)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one() or 0

    query = query.order_by(AIConsultation.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(c.id),
                "strategy_id": str(c.strategy_id),
                "recommendation": c.recommendation,
                "confidence": float(c.confidence_score or 0),
                "reasoning": c.reasoning,
                "is_error": c.is_error,
                "created_at": c.created_at.isoformat(),
            }
            for c in items
        ],
    }


@router.get("/stats")
async def ai_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI 자문 통계를 반환합니다."""
    strat_ids_result = await db.execute(
        select(Strategy.id).where(Strategy.user_id == current_user.id)
    )
    user_strategy_ids = [row[0] for row in strat_ids_result.all()]

    if not user_strategy_ids:
        return {
            "total_advice": 0,
            "execute_count": 0,
            "hold_count": 0,
            "cancel_count": 0,
            "error_count": 0,
            "avg_confidence": 0.0,
        }

    result = await db.execute(
        select(AIConsultation).where(
            AIConsultation.strategy_id.in_(user_strategy_ids)
        )
    )
    consultations = result.scalars().all()

    total = len(consultations)
    execute_count = sum(1 for c in consultations if c.recommendation == "execute")
    hold_count = sum(1 for c in consultations if c.recommendation == "hold")
    cancel_count = sum(1 for c in consultations if c.recommendation == "cancel")
    error_count = sum(1 for c in consultations if c.is_error)
    scores = [float(c.confidence_score) for c in consultations if c.confidence_score]
    avg_confidence = sum(scores) / len(scores) if scores else 0.0

    return {
        "total_advice": total,
        "execute_count": execute_count,
        "hold_count": hold_count,
        "cancel_count": cancel_count,
        "error_count": error_count,
        "avg_confidence": round(avg_confidence, 4),
    }
