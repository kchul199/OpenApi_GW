"""
WebSocket Reverse Proxy Listener.
Bidirectionally proxies WebSocket messages between client and upstream.
"""
from __future__ import annotations

import asyncio
import logging

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from gateway.core.context import GatewayContext, Protocol, UpstreamInfo

logger = logging.getLogger(__name__)


class WebSocketProxy:
    """
    Proxies a WebSocket connection to an upstream WebSocket server.
    Runs two asyncio tasks — client→upstream and upstream→client — concurrently.
    """

    async def proxy(
        self,
        client_ws: WebSocket,
        upstream_url: str,
        ctx: GatewayContext,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {"X-Request-ID": ctx.request_id}
        if extra_headers:
            headers.update(extra_headers)

        # Extract client's requested subprotocols
        client_subprotocols = client_ws.headers.get("sec-websocket-protocol", "").split(",")
        client_subprotocols = [p.strip() for p in client_subprotocols if p.strip()]

        logger.info(
            "WebSocket proxy initiating",
            extra={"request_id": ctx.request_id, "upstream": upstream_url, "subprotocols": client_subprotocols},
        )
        
        try:
            # 1. Connect to upstream FIRST before accepting the client
            async with websockets.connect(
                upstream_url, 
                extra_headers=headers, 
                subprotocols=client_subprotocols if client_subprotocols else None
            ) as upstream_ws:
                
                # 2. Accept client with the subprotocol chosen by upstream
                accepted_subprotocol = upstream_ws.subprotocol
                await client_ws.accept(subprotocol=accepted_subprotocol)
                
                logger.info(
                    "WebSocket proxy connected",
                    extra={"request_id": ctx.request_id, "accepted_subprotocol": accepted_subprotocol}
                )

                # 3. Start bidirectional pumping
                await asyncio.gather(
                    self._client_to_upstream(client_ws, upstream_ws, ctx),
                    self._upstream_to_client(upstream_ws, client_ws, ctx),
                    return_exceptions=True,
                )
        except (ConnectionClosed, WebSocketDisconnect):
            pass
        except Exception as exc:
            logger.error(f"WebSocket upstream connection failed: {exc}", extra={"request_id": ctx.request_id})
        finally:
            try:
                # If we haven't accepted yet (upstream failed), close with error
                if client_ws.client_state.value == 0:  # ENUM 0 = CONNECTING
                    await client_ws.close(code=1011) # Internal Error
                else:
                    await client_ws.close()
            except Exception:
                pass
            logger.info("WebSocket proxy closed", extra={"request_id": ctx.request_id})

    @staticmethod
    async def _client_to_upstream(client: WebSocket, upstream, ctx: GatewayContext) -> None:
        try:
            while True:
                message = await client.receive()
                if "text" in message and message["text"] is not None:
                    await upstream.send(message["text"])
                elif "bytes" in message and message["bytes"] is not None:
                    await upstream.send(message["bytes"])
                elif message["type"] == "websocket.disconnect":
                    break
        except (WebSocketDisconnect, ConnectionClosed):
            logger.debug("Client→Upstream pipe closed", extra={"request_id": ctx.request_id})

    @staticmethod
    async def _upstream_to_client(upstream, client: WebSocket, ctx: GatewayContext) -> None:
        try:
            async for message in upstream:
                if isinstance(message, bytes):
                    await client.send_bytes(message)
                else:
                    await client.send_text(message)
        except (ConnectionClosed, WebSocketDisconnect):
            logger.debug("Upstream→Client pipe closed", extra={"request_id": ctx.request_id})
