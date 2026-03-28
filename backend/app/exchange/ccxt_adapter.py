"""ccxt 기반 거래소 추상화 어댑터.

ALLOWED_EXCHANGE_IDS 화이트리스트를 통해 허가된 거래소만 연결하며,
테스트넷 URL을 자동 적용합니다. 모든 API 호출은 ccxt.async_support를
사용해 asyncio 이벤트 루프에서 논블로킹으로 실행됩니다.
"""
from __future__ import annotations

import logging

import ccxt.async_support as ccxt

from app.config import ALLOWED_EXCHANGE_IDS, settings
from app.core.exceptions import ExchangeException

logger = logging.getLogger(__name__)

# 거래소별 테스트넷 엔드포인트 매핑
TESTNET_URLS: dict[str, dict[str, str]] = {
    "binance": {
        "apiURL": "https://testnet.binance.vision/api",
        "fapiURL": "https://testnet.binancefuture.com/fapi",
    },
}


class CcxtAdapter:
    """ccxt 거래소 클라이언트 래퍼.

    Args:
        exchange_id: 거래소 식별자 (ALLOWED_EXCHANGE_IDS 에 포함되어야 함)
        api_key:     거래소 API Key (복호화된 평문)
        api_secret:  거래소 API Secret (복호화된 평문)
        testnet:     테스트넷 사용 여부

    Raises:
        ValueError: exchange_id 가 ALLOWED_EXCHANGE_IDS 에 없을 때
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
    ) -> None:
        if exchange_id not in ALLOWED_EXCHANGE_IDS:
            raise ValueError(
                f"Exchange '{exchange_id}' is not in the allowlist "
                f"{ALLOWED_EXCHANGE_IDS}"
            )

        exchange_class = getattr(ccxt, exchange_id)
        params: dict = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }

        if testnet and exchange_id in TESTNET_URLS:
            params["urls"] = TESTNET_URLS[exchange_id]

        self.exchange: ccxt.Exchange = exchange_class(params)
        self.exchange_id = exchange_id
        self.testnet = testnet

        logger.info(
            "CcxtAdapter initialised",
            extra={"exchange": exchange_id, "testnet": testnet},
        )

    # ── Market Data ───────────────────────────────────────────────────────────

    async def fetch_ticker(self, symbol: str) -> dict:
        """현재가 및 24h 통계 조회."""
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            raise ExchangeException(
                f"fetch_ticker error: {e}", exchange=self.exchange_id
            ) from e

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> list:
        """OHLCV 캔들 데이터 조회.

        Returns:
            [[timestamp, open, high, low, close, volume], ...]
        """
        try:
            return await self.exchange.fetch_ohlcv(
                symbol, timeframe, limit=limit
            )
        except Exception as e:
            raise ExchangeException(
                f"fetch_ohlcv error: {e}", exchange=self.exchange_id
            ) from e

    # ── Account ───────────────────────────────────────────────────────────────

    async def fetch_balance(self) -> dict:
        """계정 잔고 조회."""
        try:
            return await self.exchange.fetch_balance()
        except Exception as e:
            raise ExchangeException(
                f"fetch_balance error: {e}", exchange=self.exchange_id
            ) from e

    # ── Orders ────────────────────────────────────────────────────────────────

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict:
        """주문 생성.

        Args:
            symbol:     거래 심볼 (예: BTC/USDT)
            order_type: 주문 유형 (market / limit / stop)
            side:       매수/매도 방향 (buy / sell)
            amount:     주문 수량 (기준 통화 단위)
            price:      주문 가격 (limit 주문 시 필수)

        Returns:
            거래소 응답 dict (id, status, filled 등)
        """
        try:
            return await self.exchange.create_order(
                symbol, order_type, side, amount, price
            )
        except Exception as e:
            raise ExchangeException(
                f"create_order error: {e}", exchange=self.exchange_id
            ) from e

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        """주문 취소."""
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            raise ExchangeException(
                f"cancel_order error: {e}", exchange=self.exchange_id
            ) from e

    async def fetch_order(self, order_id: str, symbol: str) -> dict:
        """단일 주문 조회."""
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            raise ExchangeException(
                f"fetch_order error: {e}", exchange=self.exchange_id
            ) from e

    async def fetch_open_orders(self, symbol: str | None = None) -> list:
        """미체결 주문 목록 조회.

        Args:
            symbol: 심볼 필터 (None 이면 전체 심볼)
        """
        try:
            return await self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            raise ExchangeException(
                f"fetch_open_orders error: {e}", exchange=self.exchange_id
            ) from e

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """HTTP 세션 및 WebSocket 연결 종료."""
        try:
            await self.exchange.close()
        except Exception as e:
            logger.warning("Error closing exchange session: %s", e)
