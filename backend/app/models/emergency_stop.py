"""EmergencyStop 모델 – 긴급 정지 이벤트 로그."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmergencyStop(Base):
    __tablename__ = "emergency_stops"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 트리거 원인: manual / auto_drawdown / auto_pnl / system
    trigger_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 정지 당시 포지션 처리 방법: close_all / keep / reduce
    position_action: Mapped[str] = mapped_column(String(32), nullable=False, default="close_all")

    # 재개 여부
    is_resumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="emergency_stops")
    triggered_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[triggered_by_user_id]
    )

    def __repr__(self) -> str:
        return (
            f"<EmergencyStop id={self.id} strategy={self.strategy_id} "
            f"reason={self.trigger_reason}>"
        )
