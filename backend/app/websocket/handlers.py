"""WebSocket 라우트 핸들러."""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws", tags=["websocket"])


def _get_user_id_from_token(token: str) -> str | None:
    """JWT 토큰에서 user_id 를 추출합니다."""
    try:
        payload = decode_token(token)
        return payload.get("sub")
    except Exception:
        return None


@ws_router.websocket("/prices/{symbol}")
async def price_feed(
    websocket: WebSocket,
    symbol: str,
    token: str = Query(...),
) -> None:
    """특정 심볼의 실시간 가격 피드.

    클라이언트는 JWT 토큰을 쿼리 파라미터로 전달해야 합니다.
    예: ws://host/ws/prices/BTC-USDT?token=<jwt>
    """
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = f"price:{symbol.upper()}"
    await manager.connect(websocket, [channel, f"user:{user_id}"])

    try:
        while True:
            # 클라이언트 ping 수신 (연결 유지)
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await manager.disconnect(websocket)


@ws_router.websocket("/strategies/{strategy_id}")
async def strategy_feed(
    websocket: WebSocket,
    strategy_id: str,
    token: str = Query(...),
) -> None:
    """특정 전략의 실시간 이벤트 피드 (신호, 주문 상태 변경 등).

    예: ws://host/ws/strategies/<uuid>?token=<jwt>
    """
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = f"strategy:{strategy_id}"
    await manager.connect(websocket, [channel, f"user:{user_id}"])

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await manager.disconnect(websocket)


@ws_router.websocket("/notifications")
async def notification_feed(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """사용자별 전체 알림 피드.

    예: ws://host/ws/notifications?token=<jwt>
    """
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = f"user:{user_id}"
    await manager.connect(websocket, [channel])

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await manager.disconnect(websocket)
