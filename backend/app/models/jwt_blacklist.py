"""JWTBlacklist 모델 – 로그아웃된 토큰 DB 보조 저장소.

실제 블랙리스트 조회는 Redis 에서 처리하며,
이 테이블은 Redis 장애 시 폴백 및 감사 용도로 사용됩니다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JWTBlacklist(Base):
    __tablename__ = "jwt_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # 토큰 만료 시각 (TTL 기반 정리에 활용)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_jwt_blacklist_expires_at", "expires_at"),  # 만료된 레코드 배치 삭제용
    )

    def __repr__(self) -> str:
        return f"<JWTBlacklist jti={self.jti} expires_at={self.expires_at}>"
