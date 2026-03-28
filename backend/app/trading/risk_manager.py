"""리스크 관리 서비스.

글로벌/전략별 긴급 정지 플래그 확인, 포지션/일일 거래 한도 검사,
주문 수량 계산을 담당합니다.
"""
from __future__ import annotations

import logging

from app.core.exceptions import TradingHaltedException
from app.core.redis_client import redis_exists

logger = logging.getLogger(__name__)


class RiskManager:
    """거래 전 리스크 검사 및 수량 계산 서비스."""

    # ── 거래 가능 여부 ─────────────────────────────────────────────────────────

    async def can_trade(self, strategy_id: str, user_id: str) -> None:
        """거래 가능 여부를 검사합니다.

        Redis 플래그를 확인해 글로벌 또는 전략별 긴급 정지가 활성화돼 있으면
        TradingHaltedException 을 발생시킵니다.

        Args:
            strategy_id: 전략 UUID 문자열
            user_id:     사용자 UUID 문자열 (향후 사용자별 정지 확장용)

        Raises:
            TradingHaltedException: 글로벌 또는 전략별 정지 플래그 활성 시
        """
        # 1. 글로벌 거래 정지 플래그 (운영자가 Redis 에 직접 SET)
        if await redis_exists("global:trading:halt"):
            logger.warning("Global trading halt is active")
            raise TradingHaltedException(
                f"Global trading halt is active (strategy={strategy_id})"
            )

        # 2. 전략별 긴급 정지 플래그
        if await redis_exists(f"emergency:stop:{strategy_id}"):
            logger.warning("Emergency stop active for strategy %s", strategy_id)
            raise TradingHaltedException(
                f"Strategy {strategy_id} is emergency-stopped"
            )

    # ── 한도 검사 ─────────────────────────────────────────────────────────────

    def check_position_limit(
        self,
        current_position_usdt: float,
        max_position_usdt: float,
    ) -> bool:
        """현재 포지션이 최대 허용 포지션 이하인지 확인합니다.

        Args:
            current_position_usdt: 현재 보유 포지션 평가금액 (USDT)
            max_position_usdt:     전략별 최대 포지션 한도 (USDT)

        Returns:
            True 이면 추가 주문 가능
        """
        allowed = current_position_usdt < max_position_usdt
        if not allowed:
            logger.info(
                "Position limit reached: current=%.2f max=%.2f",
                current_position_usdt,
                max_position_usdt,
            )
        return allowed

    def check_daily_limit(
        self,
        today_traded_usdt: float,
        daily_limit_usdt: float,
    ) -> bool:
        """당일 누적 거래금액이 일일 한도 이하인지 확인합니다.

        Args:
            today_traded_usdt: 오늘 체결된 총 거래금액 (USDT)
            daily_limit_usdt:  일일 거래 한도 (USDT)

        Returns:
            True 이면 추가 거래 가능
        """
        allowed = today_traded_usdt < daily_limit_usdt
        if not allowed:
            logger.info(
                "Daily limit reached: today=%.2f limit=%.2f",
                today_traded_usdt,
                daily_limit_usdt,
            )
        return allowed

    # ── 수량 계산 ─────────────────────────────────────────────────────────────

    def calculate_quantity(
        self,
        quantity_type: str,
        quantity_value: float,
        price: float,
        available_balance: float,
    ) -> float:
        """주문 수량을 계산합니다.

        Args:
            quantity_type:     수량 계산 방식
                               - ``fixed_amount``    : USDT 고정 금액으로 수량 역산
                               - ``balance_ratio``   : 가용 잔고의 일정 비율
                               - ``fixed_quantity``  : 직접 수량 지정
            quantity_value:    수량 값 (타입에 따라 USDT 금액 / 비율 / 수량)
            price:             현재가 (USDT 기준)
            available_balance: 가용 잔고 (USDT)

        Returns:
            주문 수량 (기준 통화 단위). 계산 불가 시 0.0 반환.
        """
        if price <= 0:
            logger.warning("Invalid price %.8f for quantity calculation", price)
            return 0.0

        if quantity_type == "fixed_amount":
            # 예: 100 USDT 어치 매수
            return quantity_value / price

        elif quantity_type == "balance_ratio":
            # 예: 가용 잔고의 50 % (quantity_value=0.5)
            ratio = min(max(quantity_value, 0.0), 1.0)  # 0~1 클램핑
            return (available_balance * ratio) / price

        elif quantity_type == "fixed_quantity":
            # 예: 0.01 BTC 직접 지정
            return quantity_value

        logger.warning("Unknown quantity_type: %s", quantity_type)
        return 0.0
