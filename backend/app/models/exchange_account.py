"""ExchangeAccount 모델 – 사용자의 거래소 API Key 관리."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExchangeAccount(Base):
    __tablename__ = "exchange_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    exchange_id: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "binance"
    label: Mapped[str] = mapped_column(String(128), nullable=False)        # 사용자 정의 이름

    # AES-256-GCM 암호화된 API Key / Secret
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    api_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # 일부 거래소 (Binance Sub-Account 등) 추가 패스프레이즈
    api_passphrase_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    is_testnet: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 마지막 잔고 동기화 시각
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    user: Mapped["User"] = relationship("User", back_populates="exchange_accounts")
    balances: Mapped[list["Balance"]] = relationship(
        "Balance", back_populates="exchange_account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ExchangeAccount id={self.id} exchange={self.exchange_id} label={self.label}>"
