"""Strategy 모델 – 자동 매매 전략 정의."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 기본 정보
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # e.g. BTC/USDT
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)           # e.g. 1h, 4h

    # 조건 트리 (진입/청산 조건을 JSON 트리로 표현)
    condition_tree: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # 주문 설정 (수량, 슬리피지, 손절/익절 등)
    order_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # AI 자문 모드 (0=off, 1=advisory, 2=auto)
    ai_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 전략 우선순위 (충돌 해결 시 사용)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 긴급 정지 여부
    emergency_stopped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 통계 (캐시)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(
        __import__("sqlalchemy").Numeric(20, 8), default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="strategies")
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="strategy", cascade="all, delete-orphan"
    )
    ai_consultations: Mapped[list["AIConsultation"]] = relationship(
        "AIConsultation", back_populates="strategy", cascade="all, delete-orphan"
    )
    backtest_results: Mapped[list["BacktestResult"]] = relationship(
        "BacktestResult", back_populates="strategy", cascade="all, delete-orphan"
    )
    emergency_stops: Mapped[list["EmergencyStop"]] = relationship(
        "EmergencyStop", back_populates="strategy", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Strategy id={self.id} name={self.name} symbol={self.symbol}>"
