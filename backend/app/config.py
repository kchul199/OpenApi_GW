from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import field_validator

ALLOWED_EXCHANGE_IDS: set[str] = {"binance", "upbit", "bithumb"}


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://cointrader:secret@localhost/cointrader"

    # ── Redis Sentinel ────────────────────────────────────────────────────────
    REDIS_SENTINEL_HOSTS: str = "localhost:26379"  # 콤마로 구분된 host:port 목록
    REDIS_SENTINEL_MASTER: str = "mymaster"

    # ── Auth ──────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Exchange ──────────────────────────────────────────────────────────────
    EXCHANGE_ID: str = "binance"
    USE_TESTNET: str = "true"
    QUOTE_CURRENCY: str = "USDT"

    # ── Encryption ────────────────────────────────────────────────────────────
    # 32바이트 hex 문자열(64자) → AES-256 키
    ENCRYPTION_KEY: str = "0" * 64

    # ── Claude AI ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    AI_CONSULT_TIMEOUT_SECONDS: int = 5
    AI_CONSULT_PROMPT_VERSION: int = 1

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Notifications ─────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("EXCHANGE_ID")
    @classmethod
    def validate_exchange_id(cls, v: str) -> str:
        if v not in ALLOWED_EXCHANGE_IDS:
            raise ValueError(f"EXCHANGE_ID must be one of {ALLOWED_EXCHANGE_IDS}")
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("ENCRYPTION_KEY must be 64 hex characters (32 bytes)")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("ENCRYPTION_KEY must be a valid hex string")
        return v

    # ── Computed properties ───────────────────────────────────────────────────
    @property
    def use_testnet(self) -> bool:
        return self.USE_TESTNET.lower() in ("1", "true", "yes")

    @property
    def sentinel_hosts(self) -> list[tuple[str, int]]:
        """Redis Sentinel 호스트 목록 파싱"""
        hosts: list[tuple[str, int]] = []
        for entry in self.REDIS_SENTINEL_HOSTS.split(","):
            host, port = entry.strip().split(":")
            hosts.append((host, int(port)))
        return hosts

    @property
    def encryption_key_bytes(self) -> bytes:
        return bytes.fromhex(self.ENCRYPTION_KEY)

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }


settings = Settings()
