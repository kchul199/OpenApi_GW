"""FastAPI 공통 의존성."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token, is_token_blacklisted
from app.database import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Bearer 토큰을 검증하고 현재 사용자를 반환합니다.

    Raises:
        UnauthorizedException: 토큰 없음 / 만료 / 블랙리스트 등록 / 사용자 없음
    """
    if credentials is None:
        raise UnauthorizedException("Bearer token required")

    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedException("Invalid or expired token")

    jti: str | None = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise UnauthorizedException("Token has been revoked")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise UnauthorizedException("User account is disabled")

    return user


async def get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """현재 요청의 Bearer 토큰 문자열을 반환합니다."""
    if credentials is None:
        raise UnauthorizedException("Bearer token required")
    return credentials.credentials
