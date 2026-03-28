"""보안 유틸리티.

- JWT 생성 / 검증 / 블랙리스트
- bcrypt 비밀번호 해싱
- AES-256-GCM API Key 암호화 / 복호화
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.redis_client import redis_exists, redis_setex

# ── bcrypt ────────────────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """bcrypt 해시 반환."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """평문 비밀번호와 해시 비교."""
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """JWT 생성.

    Returns:
        (token, jti) – jti 는 블랙리스트 등록 시 사용
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    """JWT 검증 후 payload 반환.

    Raises:
        jose.JWTError: 서명 오류 / 만료 등
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def get_token_expiry(payload: dict[str, Any]) -> datetime:
    """payload 의 exp 클레임을 datetime 으로 변환."""
    exp: int = payload["exp"]
    return datetime.fromtimestamp(exp, tz=timezone.utc)


# ── JWT 블랙리스트 (Redis) ────────────────────────────────────────────────────

async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """만료 시점까지 jti 를 Redis 블랙리스트에 등록."""
    ttl = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 1)
    await redis_setex(f"jwt:blacklist:{jti}", ttl, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """jti 가 블랙리스트에 존재하면 True."""
    return await redis_exists(f"jwt:blacklist:{jti}")


# ── AES-256-GCM 암호화 ────────────────────────────────────────────────────────

_NONCE_SIZE = 12  # 96-bit (GCM 권장)


def encrypt_api_key(plaintext: str) -> bytes:
    """AES-256-GCM 으로 API Key 암호화.

    반환 형식: nonce(12 bytes) ‖ tag(16 bytes) ‖ ciphertext
    (AESGCM.encrypt 가 ciphertext + tag 를 붙여서 반환하므로
     실제 bytes = nonce + aesgcm.encrypt(...) )
    """
    aesgcm = AESGCM(settings.encryption_key_bytes)
    nonce = uuid.uuid4().bytes[:_NONCE_SIZE]  # 무작위 96-bit nonce
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext_with_tag


def decrypt_api_key(encrypted: bytes) -> str:
    """AES-256-GCM 복호화.

    Args:
        encrypted: ``encrypt_api_key`` 의 반환값

    Returns:
        복호화된 평문 문자열

    Raises:
        cryptography.exceptions.InvalidTag: 무결성 검증 실패
    """
    aesgcm = AESGCM(settings.encryption_key_bytes)
    nonce = encrypted[:_NONCE_SIZE]
    ciphertext_with_tag = encrypted[_NONCE_SIZE:]
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return plaintext_bytes.decode("utf-8")
