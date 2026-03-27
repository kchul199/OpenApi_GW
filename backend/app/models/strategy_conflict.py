"""StrategyConflict 모델 – 전략 간 충돌 기록."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StrategyConflict(Base):
    """두 전략이 동일 심볼에서 반대 방향 신호를 낼 때 기록됩니다."""

    __tablename__ = "strategy_conflicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 충돌 당사자
    strategy_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 각 전략의 신호
    signal_a: Mapped[str] = mapped_column(String(16), nullable=False)  # buy / sell
    signal_b: Mapped[str] = mapped_column(String(16), nullable=False)

    # 해결 방식: priority / paused / manual
    resolution: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    # 우선권을 획득한 전략 (해결된 경우)
    winner_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    strategy_a: Mapped["Strategy"] = relationship(
        "Strategy", foreign_keys=[strategy_a_id]
    )
    strategy_b: Mapped["Strategy"] = relationship(
        "Strategy", foreign_keys=[strategy_b_id]
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyConflict symbol={self.symbol} "
            f"a={self.strategy_a_id} b={self.strategy_b_id} resolution={self.resolution}>"
        )
