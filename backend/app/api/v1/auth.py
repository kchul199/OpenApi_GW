"""인증 API 라우터.

엔드포인트:
    POST /auth/register  – 회원가입
    POST /auth/login     – 로그인 (JWT 발급)
    POST /auth/logout    – 로그아웃 (JWT 블랙리스트)
    POST /auth/2fa/setup – TOTP 설정
    POST /auth/2fa/verify – TOTP 검증
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from typing import Annotated

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import (
    blacklist_token,
    create_access_token,
    decode_token,
    get_token_expiry,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.dependencies import get_current_token, get_current_user
from app.models.jwt_blacklist import JWTBlacklist
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """신규 사용자 등록."""
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise ConflictException("Email already registered")

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    return {"message": "registered"}


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """이메일/비밀번호로 로그인하고 JWT를 반환합니다."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise UnauthorizedException("Invalid credentials")

    if not user.is_active:
        raise UnauthorizedException("Account is disabled")

    # TOTP 2FA 검증
    if user.totp_secret and user.totp_enabled:
        if not req.totp_code:
            raise UnauthorizedException("2FA code required")
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(req.totp_code, valid_window=1):
            raise UnauthorizedException("Invalid 2FA code")

    token, _jti = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    token: Annotated[str, Depends(get_current_token)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """현재 토큰을 블랙리스트에 등록하여 로그아웃합니다."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedException("Invalid token")

    jti: str = payload.get("jti", "")
    expires_at: datetime = get_token_expiry(payload)

    # Redis 블랙리스트 등록
    await blacklist_token(jti, expires_at)

    # DB 보조 저장 (감사 로그 / Redis 장애 폴백)
    blacklist_entry = JWTBlacklist(
        jti=jti,
        expires_at=expires_at,
        blacklisted_at=datetime.now(timezone.utc),
    )
    db.add(blacklist_entry)
    await db.commit()

    return {"message": "logged out"}


@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> TOTPSetupResponse:
    """TOTP 시크릿을 생성하고 QR 코드를 반환합니다.

    이 엔드포인트를 호출하면 새로운 TOTP 시크릿이 발급되며,
    /auth/2fa/verify 로 검증 후 활성화됩니다.
    """
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="CoinTrader",
    )

    # QR 코드 PNG → base64
    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    # 시크릿 임시 저장 (아직 totp_enabled=False)
    current_user.totp_secret = secret
    current_user.totp_enabled = False
    await db.commit()

    return TOTPSetupResponse(
        qr_url=f"data:image/png;base64,{qr_b64}",
        secret=secret,
    )


@router.post("/2fa/verify")
async def verify_2fa(
    req: TOTPVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """TOTP 코드를 검증하고 2FA를 활성화합니다."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not set up. Call /auth/2fa/setup first.")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(req.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    current_user.totp_enabled = True
    await db.commit()

    return {"message": "2FA enabled successfully"}


@router.delete("/2fa/disable")
async def disable_2fa(
    req: TOTPVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """현재 TOTP 코드를 확인 후 2FA를 비활성화합니다."""
    if not current_user.totp_secret or not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(req.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    current_user.totp_secret = None
    current_user.totp_enabled = False
    await db.commit()

    return {"message": "2FA disabled"}
