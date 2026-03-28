"""시장 데이터 API – 캔들 및 현재가."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.core.exceptions import BadRequestException
from app.dependencies import get_current_user
from app.exchange.ccxt_adapter import CcxtAdapter
from app.models.user import User

router = APIRouter(prefix="/market", tags=["market"])


def _get_adapter() -> CcxtAdapter:
    """설정 기반 기본 거래소 어댑터를 반환합니다."""
    return CcxtAdapter(
        exchange_id=settings.EXCHANGE_ID,
        api_key="",
        api_secret="",
        testnet=settings.use_testnet,
    )


@router.get("/candles")
async def get_candles(
    current_user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query(..., description="거래 심볼 (예: BTC/USDT)"),
    interval: str = Query("1h", description="타임프레임 (예: 1m, 5m, 1h, 4h, 1d)"),
    limit: int = Query(200, ge=10, le=1000),
) -> list[dict]:
    """OHLCV 캔들 데이터를 반환합니다."""
    adapter = _get_adapter()
    try:
        raw = await adapter.fetch_ohlcv(symbol, interval, limit=limit)
    finally:
        await adapter.close()

    return [
        {
            "time": int(c[0] // 1000),  # unix seconds (lightweight-charts 호환)
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5],
        }
        for c in raw
    ]


@router.get("/price/{symbol:path}")
async def get_price(
    symbol: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """특정 심볼의 현재가 및 24h 변동률을 반환합니다."""
    adapter = _get_adapter()
    try:
        ticker = await adapter.fetch_ticker(symbol)
    finally:
        await adapter.close()

    return {
        "symbol": symbol,
        "price": ticker.get("last") or ticker.get("close", 0),
        "change_24h": ticker.get("percentage", 0),
        "high_24h": ticker.get("high", 0),
        "low_24h": ticker.get("low", 0),
        "volume_24h": ticker.get("quoteVolume", 0),
    }
