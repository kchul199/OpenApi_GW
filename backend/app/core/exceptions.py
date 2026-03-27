"""애플리케이션 커스텀 예외 계층.

HTTP 예외: FastAPI HTTPException 을 상속하여 상태 코드를 고정.
도메인 예외: 순수 Python Exception – 서비스 계층에서 발생, 라우터에서 HTTPException 으로 변환.
"""
from __future__ import annotations

from fastapi import HTTPException, status


# ── HTTP 예외 ─────────────────────────────────────────────────────────────────

class UnauthorizedException(HTTPException):
    """401 Unauthorized – 인증 실패 또는 토큰 없음."""

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(HTTPException):
    """403 Forbidden – 권한 부족."""

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundException(HTTPException):
    """404 Not Found."""

    def __init__(self, detail: str = "Not found") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ConflictException(HTTPException):
    """409 Conflict – 중복 리소스 등."""

    def __init__(self, detail: str = "Conflict") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class BadRequestException(HTTPException):
    """400 Bad Request – 요청 파라미터 오류."""

    def __init__(self, detail: str = "Bad request") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class UnprocessableException(HTTPException):
    """422 Unprocessable Entity – 비즈니스 로직 유효성 오류."""

    def __init__(self, detail: str = "Unprocessable entity") -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class ServiceUnavailableException(HTTPException):
    """503 Service Unavailable – 외부 의존 서비스 장애."""

    def __init__(self, detail: str = "Service unavailable") -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


# ── 도메인 예외 (서비스 계층) ─────────────────────────────────────────────────

class TradingHaltedException(Exception):
    """긴급 정지(Emergency Stop) 플래그 활성화 시 발생."""

    def __init__(self, strategy_id: int | None = None) -> None:
        msg = "Trading is halted"
        if strategy_id is not None:
            msg = f"Trading is halted for strategy {strategy_id}"
        super().__init__(msg)
        self.strategy_id = strategy_id


class ExchangeException(Exception):
    """거래소 API 오류 (ccxt 예외 래핑 등)."""

    def __init__(self, detail: str, exchange: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.exchange = exchange


class InsufficientBalanceException(Exception):
    """잔고 부족으로 주문 불가."""

    def __init__(self, required: float, available: float, currency: str = "USDT") -> None:
        super().__init__(
            f"Insufficient balance: required {required} {currency}, available {available} {currency}"
        )
        self.required = required
        self.available = available
        self.currency = currency


class StrategyConflictException(Exception):
    """전략 간 심볼/방향 충돌."""

    def __init__(self, conflicting_strategy_id: int, symbol: str) -> None:
        super().__init__(
            f"Strategy conflict on {symbol} with strategy {conflicting_strategy_id}"
        )
        self.conflicting_strategy_id = conflicting_strategy_id
        self.symbol = symbol


class BacktestException(Exception):
    """백테스트 실행 오류."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
