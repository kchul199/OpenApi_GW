"""BacktestResult 모델 – 백테스트 결과 저장."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 백테스트 파라미터
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    initial_capital: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    commission_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False, default=0.001)
    slippage_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False, default=0.0005)

    # 상태: pending / running / completed / failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 성과 지표 (완료 후 채워짐)
    final_capital: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)
    total_return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    sortino_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    avg_holding_hours: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # 상세 트레이드 목록 (JSON)
    trades_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 에러 메시지 (실패 시)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="backtest_results")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<BacktestResult id={self.id} strategy={self.strategy_id} status={self.status}>"
        )
