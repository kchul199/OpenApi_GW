"""전략 충돌 감지 서비스.

동일 사용자가 소유한 활성 전략들 중, 같은 심볼에서 반대 방향 신호가
동시에 발생할 때 충돌을 감지하고 우선순위(priority) 기반으로 해결합니다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy
from app.models.strategy_conflict import StrategyConflict

logger = logging.getLogger(__name__)


class ConflictService:
    """전략 충돌 감지 및 해결."""

    async def detect_and_resolve(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        pending_signals: dict[uuid.UUID, str],
    ) -> list[StrategyConflict]:
        """동시 신호 사전에서 충돌을 감지하고 DB 에 기록합니다.

        Args:
            db:              비동기 DB 세션
            user_id:         신호를 발생시킨 사용자 ID
            pending_signals: {strategy_id: signal("buy"/"sell")} 형태의 dict

        Returns:
            감지된 StrategyConflict 목록
        """
        if len(pending_signals) < 2:
            return []

        # 활성 전략 조회 (symbol + priority 정보 필요)
        strategy_ids = list(pending_signals.keys())
        result = await db.execute(
            select(Strategy).where(
                Strategy.id.in_(strategy_ids),
                Strategy.user_id == user_id,
                Strategy.is_active == True,
                Strategy.emergency_stopped == False,
            )
        )
        strategies: dict[uuid.UUID, Strategy] = {s.id: s for s in result.scalars().all()}

        conflicts: list[StrategyConflict] = []

        for id_a, id_b in combinations(strategy_ids, 2):
            sig_a = pending_signals[id_a]
            sig_b = pending_signals[id_b]

            strat_a = strategies.get(id_a)
            strat_b = strategies.get(id_b)

            if strat_a is None or strat_b is None:
                continue

            # 같은 심볼, 반대 방향 → 충돌
            if strat_a.symbol != strat_b.symbol:
                continue
            if sig_a == sig_b:
                continue

            logger.warning(
                "Conflict detected: strategy %s (%s) vs %s (%s) on %s",
                id_a, sig_a, id_b, sig_b, strat_a.symbol,
            )

            # 우선순위 기반 해결: 더 높은 priority 가 승리
            if strat_a.priority >= strat_b.priority:
                winner_id = id_a
            else:
                winner_id = id_b

            conflict = StrategyConflict(
                id=uuid.uuid4(),
                strategy_a_id=id_a,
                strategy_b_id=id_b,
                symbol=strat_a.symbol,
                signal_a=sig_a,
                signal_b=sig_b,
                resolution="priority",
                winner_strategy_id=winner_id,
                notes=(
                    f"Auto-resolved by priority: "
                    f"strategy_a.priority={strat_a.priority}, "
                    f"strategy_b.priority={strat_b.priority}"
                ),
                detected_at=datetime.now(timezone.utc),
                resolved_at=datetime.now(timezone.utc),
            )
            db.add(conflict)
            conflicts.append(conflict)

        if conflicts:
            await db.flush()

        return conflicts

    async def get_conflicts(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[StrategyConflict]:
        """사용자의 전략 충돌 이력을 반환합니다."""
        # 사용자 전략 ID 목록 조회
        strat_ids_result = await db.execute(
            select(Strategy.id).where(Strategy.user_id == user_id)
        )
        user_strategy_ids = {row[0] for row in strat_ids_result.all()}

        if not user_strategy_ids:
            return []

        result = await db.execute(
            select(StrategyConflict)
            .where(StrategyConflict.strategy_a_id.in_(user_strategy_ids))
            .order_by(StrategyConflict.detected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
