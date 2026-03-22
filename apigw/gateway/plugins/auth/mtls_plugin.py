"""
mTLS Enforcer Plugin.
Verifies client certificates. Usually, the actual TLS termination happens at the 
edge load balancer (e.g., Nginx, Envoy, AWS ALB) which forwards the client cert 
details via a specific HTTP header (like `X-Client-Cert` or `X-Forwarded-Client-Cert`).
This plugin parses and validates that header.
"""
import logging
from fastapi import Request, Response
from gateway.core.context import AuthMethod, GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)

@PluginRegistry.register
class MTLSEnforcerPlugin(BasePlugin):
    name = "mtls-enforcer"
    order = 5  # Run before JWT or other auth plugins

    def configure(self, config: dict) -> None:
        # Default header injected by the Edge proxy containing the client cert or its Subject DN
        self._cert_header: str = config.get("cert_header", "x-client-cert")
        # Optional: Require specific Subject DNs
        self._allowed_subjects: list[str] = config.get("allowed_subjects", [])

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        client_cert = request.headers.get(self._cert_header)

        if not client_cert:
            logger.warning("mTLS Enforcer: Missing client certificate header.", extra={"request_id": ctx.request_id})
            return Response(
                content='{"detail":"mTLS client certificate required"}',
                status_code=401,
                media_type="application/json"
            )

        # Basic validation of allowed subjects if configured
        if self._allowed_subjects:
            # In a real-world scenario, the proxy injects URL-encoded PEM or DN string.
            # We do a simple substring match for structural demonstration.
            is_allowed = any(subj in client_cert for subj in self._allowed_subjects)
            if not is_allowed:
                logger.warning(f"mTLS: Certificate subject not in allowed list: {client_cert}")
                return Response(
                    content='{"detail":"Client certificate not authorized"}',
                    status_code=403,
                    media_type="application/json"
                )

        ctx.auth_method = AuthMethod.MTLS
        ctx.principal = client_cert[:50] + "..." if len(client_cert) > 50 else client_cert
        
        logger.debug(f"mTLS Validation successful for request {ctx.request_id}")
        return await next(request, ctx)
