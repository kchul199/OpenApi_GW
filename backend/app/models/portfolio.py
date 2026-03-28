"""Portfolio 모델 – 포지션 및 평가손익 현황."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Portfolio(Base):
    __tablename__ = "portfolio"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    exchange_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)

    # 포지션 방향: long / short
    side: Mapped[str] = mapped_column(String(8), nullable=False)

    # 평균 진입가
    entry_price: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)

    # 현재 시장가 (최근 업데이트)
    current_price: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)

    # 미실현 손익
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)
    unrealized_pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # 누적 실현 손익
    realized_pnl: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False, default=0)

    # 레버리지 (현물이면 1)
    leverage: Mapped[int] = mapped_column(nullable=False, default=1)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_portfolio_user_symbol", "user_id", "symbol"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User")
    strategy: Mapped["Strategy | None"] = relationship("Strategy")

    def __repr__(self) -> str:
        return (
            f"<Portfolio user={self.user_id} symbol={self.symbol} "
            f"side={self.side} qty={self.quantity}>"
        )
