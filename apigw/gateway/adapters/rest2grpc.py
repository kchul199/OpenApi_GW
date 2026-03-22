"""
REST to gRPC Protocol Adapter.
Converts incoming HTTP/REST JSON payloads to upstream gRPC calls.
"""
import json
import logging
from typing import Any

import grpc
from fastapi import Request
from fastapi.responses import JSONResponse

from gateway.core.context import UpstreamInfo

logger = logging.getLogger(__name__)


class RestToGrpcAdapter:
    """
    Adapter to convert REST requests to gRPC calls.
    
    NOTE: In a fully dynamic gateway, this requires either:
    1. Upstream Server Reflection to dynamically build Protobuf messages from JSON.
    2. A pre-compiled Protobuf descriptor registry mapping route IDs to message classes.
    
    This is a structural implementation that demonstrates the conversion pipeline.
    """

    def __init__(self, reflection_enabled: bool = False):
        self.reflection_enabled = reflection_enabled
        self._channel_pool: dict[str, grpc.aio.Channel] = {}

    def _get_channel(self, target: str) -> grpc.aio.Channel:
        if target not in self._channel_pool:
            # Strip grpc:// prefix if present
            clean_target = target.replace("grpc://", "")
            self._channel_pool[target] = grpc.aio.insecure_channel(clean_target)
        return self._channel_pool[target]

    async def handle_request(
        self, request: Request, upstream: UpstreamInfo, grpc_method: str
    ) -> JSONResponse:
        """
        Handles the REST request, proxies to gRPC, and returns a JSON response.
        :param grpc_method: The fully qualified gRPC method name, e.g., '/helloworld.Greeter/SayHello'
        """
        channel = self._get_channel(upstream.url)
        
        try:
            # 1. Parse REST Payload (JSON)
            body_bytes = await request.body()
            payload = json.loads(body_bytes) if body_bytes else {}
            
            # 2. Serialize JSON to Protobuf
            # To make this fully generic, we would use google.protobuf.json_format
            # combined with the descriptor of the target gRPC method.
            # Here, we assume a pass-through of bytes for the sake of the structural proxy,
            # or require the user to register the specific serializers in a real deployment.
            
            # Fallback mock for demonstration (sending raw bytes or pre-serialized)
            # In a real dynamic scenario, we'd use reflection to get the message type:
            # message_class = get_message_class_from_reflection(channel, grpc_method)
            # proto_msg = json_format.ParseDict(payload, message_class())
            # serialized_data = proto_msg.SerializeToString()
            
            serialized_data = json.dumps(payload).encode("utf-8") # Mock binary payload
            
            # 3. Invoke gRPC Call
            call = channel.unary_unary(
                grpc_method,
                request_serializer=lambda x: x,  # Bypass serializer
                response_deserializer=lambda x: x # Bypass deserializer
            )
            
            metadata = []
            for k, v in request.headers.items():
                if k.lower() not in ("host", "content-length", "content-type"):
                    metadata.append((k.lower(), v))

            response_bytes = await call(serialized_data, metadata=metadata)
            
            # 4. Deserialize Protobuf to JSON
            # json_response_dict = json_format.MessageToDict(response_bytes)
            try:
                # Attempt to parse mock response
                json_response_dict = json.loads(response_bytes.decode("utf-8"))
            except Exception:
                json_response_dict = {"raw_payload": response_bytes.hex()}
                
            return JSONResponse(content=json_response_dict, status_code=200)

        except grpc.aio.AioRpcError as e:
            logger.error(f"REST->gRPC translation failed: {e.code()} - {e.details()}")
            return JSONResponse(
                content={"error": "gRPC upstream error", "details": e.details(), "code": e.code().name},
                status_code=502
            )
        except json.JSONDecodeError:
            return JSONResponse(
                content={"error": "Invalid JSON payload"},
                status_code=400
            )
        except Exception as e:
            logger.exception("Unexpected error in REST->gRPC adapter")
            return JSONResponse(
                content={"error": "Internal Adapter Error"},
                status_code=500
            )

    async def close(self):
        for channel in self._channel_pool.values():
            await channel.close()
