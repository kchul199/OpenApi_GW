"""SQLAlchemy 비동기 엔진 및 세션 팩토리."""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,           # 커넥션 재사용 전 ping
    pool_recycle=3600,            # 1시간마다 커넥션 갱신
)

# ── Session Factory ────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Declarative Base ──────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """모든 ORM 모델의 기본 클래스."""
    pass


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI DI 용 비동기 세션 제공자.

    세션 내에서 예외가 발생하면 자동으로 롤백하고,
    ``finally`` 에서 세션을 닫습니다.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
