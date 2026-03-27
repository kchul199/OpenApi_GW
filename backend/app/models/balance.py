"""Balance 모델 – 거래소 계정 잔고 스냅샷."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Balance(Base):
    __tablename__ = "balances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exchange_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    currency: Mapped[str] = mapped_column(String(16), nullable=False)  # BTC, ETH, USDT ...
    free: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False, default=0)
    locked: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(28, 8), nullable=False, default=0)

    # USDT 기준 평가 금액
    usd_value: Mapped[float | None] = mapped_column(Numeric(28, 8), nullable=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_balance_account_currency", "exchange_account_id", "currency"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    exchange_account: Mapped["ExchangeAccount"] = relationship(
        "ExchangeAccount", back_populates="balances"
    )

    def __repr__(self) -> str:
        return (
            f"<Balance account={self.exchange_account_id} "
            f"currency={self.currency} total={self.total}>"
        )
