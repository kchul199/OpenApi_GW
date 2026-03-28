"""Candle 모델 – OHLCV 캔들 데이터 저장."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    exchange_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)  # 1m, 5m, 1h, 4h, 1d

    # 캔들 시작 시각 (UTC)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    open: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False)

    # 거래 건수 (일부 거래소 제공)
    trade_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "exchange_id", "symbol", "timeframe", "open_time",
            name="uq_candle_exchange_symbol_timeframe_open_time",
        ),
        Index("ix_candle_lookup", "exchange_id", "symbol", "timeframe", "open_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<Candle {self.exchange_id} {self.symbol} {self.timeframe} {self.open_time} "
            f"O={self.open} H={self.high} L={self.low} C={self.close}>"
        )
