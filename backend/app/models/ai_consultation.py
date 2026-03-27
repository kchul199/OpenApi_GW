"""AIConsultation 모델 – Claude AI 자문 기록."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AIConsultation(Base):
    __tablename__ = "ai_consultations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 요청 프롬프트 버전
    prompt_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # 입력 컨텍스트 (시장 데이터 요약 등)
    input_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # AI 응답
    recommendation: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # buy / sell / hold / close
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)  # 0~1
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 실제 채택 여부
    was_adopted: Mapped[bool | None] = mapped_column(nullable=True)

    # 응답 소요 시간 (ms)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 오류 여부
    is_error: Mapped[bool] = mapped_column(nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="ai_consultations")

    def __repr__(self) -> str:
        return (
            f"<AIConsultation id={self.id} strategy={self.strategy_id} "
            f"recommendation={self.recommendation}>"
        )
