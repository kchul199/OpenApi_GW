"""WebSocket 연결 관리자."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 연결 풀 및 메시지 브로드캐스트.

    채널 기반 구독 모델:
        - ``price:{symbol}``   : 특정 심볼 실시간 가격
        - ``strategy:{id}``    : 특정 전략 이벤트 (신호, 주문)
        - ``user:{user_id}``   : 사용자별 전체 알림
    """

    def __init__(self) -> None:
        # channel → set of WebSocket
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        # WebSocket → set of channel
        self._socket_channels: dict[WebSocket, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channels: list[str]) -> None:
        """WebSocket 연결 수락 및 채널 구독."""
        await websocket.accept()
        async with self._lock:
            for ch in channels:
                self._channels[ch].add(websocket)
                self._socket_channels[websocket].add(ch)
        logger.debug("WS connected, channels=%s", channels)

    async def disconnect(self, websocket: WebSocket) -> None:
        """연결 종료 및 채널 구독 해제."""
        async with self._lock:
            for ch in self._socket_channels.pop(websocket, set()):
                self._channels[ch].discard(websocket)
                if not self._channels[ch]:
                    del self._channels[ch]
        logger.debug("WS disconnected")

    async def broadcast(self, channel: str, message: Any) -> None:
        """특정 채널의 모든 구독자에게 메시지를 전송합니다."""
        sockets = set(self._channels.get(channel, set()))
        if not sockets:
            return

        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, message: Any) -> None:
        """특정 WebSocket 에만 메시지를 전송합니다."""
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    def subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


# 전역 연결 관리자 싱글턴
manager = ConnectionManager()
