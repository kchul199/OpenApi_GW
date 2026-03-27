"""Order 모델 – 주문 기록."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 거래소 식별
    exchange_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # 주문 정보
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)      # buy / sell
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)  # market / limit / stop

    # 가격 / 수량
    price: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Numeric(28, 8), default=0, nullable=False)
    average_fill_price: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)

    # 수수료
    fee: Mapped[float] = mapped_column(Numeric(20, 8), default=0, nullable=False)
    fee_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # 상태: open / closed / canceled / partially_filled / rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)

    # 실현 손익 (청산 시점에 기록)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)

    # 원인 (signal, ai_advisory, manual, emergency_stop 등)
    trigger_source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 부가 정보 (거래소 응답 원문 등)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    strategy: Mapped["Strategy | None"] = relationship("Strategy", back_populates="orders")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} symbol={self.symbol} side={self.side} status={self.status}>"
        )
