# CLAUDE.md — Open API Gateway (OAG)

This file provides guidance for AI assistants working in this codebase.

## Project Overview

Open API Gateway (OAG) is a production-ready API gateway built with Python/FastAPI that supports HTTP/REST, gRPC, and WebSocket protocols. It features a plugin-based middleware system, Redis-backed distributed state, hot-reload configuration, and full observability (Prometheus + OpenTelemetry).

**Python version required:** 3.11+

---

## Repository Layout

```
/
├── apigw/                        # Main application root
│   ├── gateway/                  # Gateway microservice
│   │   ├── main.py               # Uvicorn/Gunicorn entry point
│   │   ├── app.py                # FastAPI app factory (lifespan, routes)
│   │   ├── config/               # Configuration loading & watching
│   │   │   ├── settings.py       # Pydantic settings (env vars)
│   │   │   ├── loader.py         # YAML config loader (routes & gateway)
│   │   │   └── watcher.py        # File system watcher for hot-reload
│   │   ├── core/                 # Core engine components
│   │   │   ├── router.py         # Dynamic routing engine
│   │   │   ├── proxy.py          # HTTP reverse proxy (httpx)
│   │   │   ├── redis.py          # Redis client initialization
│   │   │   ├── context.py        # Per-request GatewayContext
│   │   │   └── pipeline.py       # Middleware plugin pipeline
│   │   ├── listeners/            # Protocol-specific servers
│   │   │   ├── grpc_listener.py  # gRPC server (port 9090)
│   │   │   └── websocket_listener.py # WebSocket bidirectional proxy
│   │   ├── adapters/             # Protocol conversion
│   │   │   ├── grpc_proxy.py     # Generic gRPC reverse proxy
│   │   │   └── rest2grpc.py      # REST-to-gRPC adapter
│   │   ├── plugins/              # Middleware plugin system
│   │   │   ├── base.py           # BasePlugin & PluginRegistry
│   │   │   ├── auth/             # JWT, API Key, mTLS plugins
│   │   │   ├── ratelimit/        # Redis Token Bucket rate limiter
│   │   │   ├── circuitbreaker/   # Distributed circuit breaker
│   │   │   └── logging/          # Request ID & access logger plugins
│   │   └── observability/        # Metrics, tracing, structured logging
│   ├── admin/
│   │   └── app.py                # Admin control plane API (port 9000)
│   ├── config/
│   │   ├── gateway.yaml          # Global plugin configuration
│   │   └── routes.yaml           # Route definitions
│   ├── tests/
│   │   └── load/                 # k6 load testing scripts
│   ├── docs/
│   │   ├── architecture.md       # System design & internals
│   │   └── api_spec.md           # API specs & plugin reference
│   ├── deployments/
│   │   ├── Dockerfile            # Multi-stage build (python:3.11-slim)
│   │   ├── docker-compose.yaml   # Full stack (gateway, admin, redis, prometheus, grafana)
│   │   └── kubernetes/base/      # K8s manifests (namespace → HPA/PDB)
│   ├── requirements.txt          # Python dependencies
│   └── pyproject.toml            # Project metadata & tool config
├── workfoot.md                   # Development log (Korean)
└── README.md                     # User-facing docs (Korean)
```

---

## Development Workflow

### Setup

```bash
cd apigw
pip install -r requirements.txt
```

### Running Locally

```bash
# Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# Start gateway
cd apigw
python -m gateway.main

# Start admin API (separate process)
cd apigw
python -m admin.app
```

### Running via Docker Compose (recommended)

```bash
cd apigw/deployments
docker-compose up
```

Services:
- Gateway: http://localhost:8080
- Admin API: http://localhost:9000
- Prometheus: http://localhost:9091
- Grafana: http://localhost:3000 (admin/admin)
- Mock upstream: http://localhost:8000

### Health & Readiness Checks

```bash
curl http://localhost:8080/_health   # Checks Redis connectivity
curl http://localhost:8080/_ready    # Simple readiness probe
```

### Config Hot-Reload

```bash
# Via Admin API
curl -X POST http://localhost:9000/api/v1/reload \
  -H "X-Admin-Key: changeme-admin-key"

# Or edit config/routes.yaml — file watcher polls every 5s
```

---

## Key Conventions

### Plugin Development

All plugins must extend `BasePlugin` from `gateway/plugins/base.py`:

```python
from gateway.plugins.base import BasePlugin, PluginRegistry
from starlette.requests import Request
from gateway.core.context import GatewayContext

class MyPlugin(BasePlugin):
    name = "my-plugin"   # Must be unique; used in routes.yaml
    order = 100          # Lower order = runs earlier in pipeline

    def configure(self, config: dict) -> None:
        # Parse plugin-specific config here
        pass

    async def __call__(self, request: Request, ctx: GatewayContext, next) -> Response:
        # Pre-processing
        response = await next(request, ctx)
        # Post-processing
        return response

PluginRegistry.register(MyPlugin)
```

Register the plugin by importing the module in `app.py`.

### Route Configuration (`config/routes.yaml`)

```yaml
routes:
  - id: my-service-v1           # Unique identifier
    description: "My service"
    match:
      protocol: HTTP            # HTTP | gRPC | WebSocket
      path: /api/v1/my/**       # Exact, prefix (/**), or regex (~pattern)
      methods: [GET, POST]
      headers: {}               # Optional header matching
    upstream:
      type: REST
      targets:
        - url: http://my-service:8080
          weight: 100
      timeout: 30.0
      retry:
        count: 3
        backoff_factor: 0.3
        status_codes: [502, 503, 504]
      load_balance: round_robin  # round_robin | random | ip_hash | least_connections
    plugins:
      - name: jwt-validator
        enabled: true
        config:
          secret_key: "your-secret"
          algorithm: HS256
      - name: rate-limiter
        enabled: true
        config:
          limit: 1000
          window: 60
          key_func: user         # ip | user | api_key
    strip_prefix: false
    preserve_host: false
```

**Route matching is first-match-wins.** Order routes from most specific to least specific.

### Environment Variables

Settings use Pydantic's nested delimiter (`__`):

| Variable | Default | Description |
|---|---|---|
| `SERVER__PORT` | `8080` | HTTP listen port |
| `SERVER__GRPC_PORT` | `9090` | gRPC listen port |
| `SERVER__WORKERS` | `1` | Gunicorn workers |
| `REDIS__URL` | `redis://localhost:6379/0` | Redis connection URL |
| `REDIS__CLUSTER_MODE` | `False` | Enable Redis Cluster |
| `OBSERVABILITY__LOG_LEVEL` | `INFO` | Logging level |
| `OBSERVABILITY__LOG_FORMAT` | `json` | `json` or `text` |
| `OBSERVABILITY__TRACING_ENABLED` | `True` | Enable OTEL tracing |
| `OBSERVABILITY__OTEL_EXPORTER_ENDPOINT` | `http://localhost:4317` | OTLP endpoint |
| `ADMIN__PORT` | `9000` | Admin API port |
| `ADMIN__API_KEY` | `changeme-admin-key` | Admin auth key |
| `ROUTES_CONFIG` | `config/routes.yaml` | Routes file path |
| `GATEWAY_CONFIG` | `config/gateway.yaml` | Gateway config path |

Place overrides in a `.env` file at `apigw/`.

### Request Flow

```
Incoming Request
    ↓
Route Matching (router.py)       ← exact / prefix / regex
    ↓
Upstream Resolution              ← load balancing
    ↓
Plugin Pipeline (pipeline.py)
  ├── Global plugins (gateway.yaml order)
  │     └── request-id → access-logger → ...
  └── Per-route plugins (routes.yaml order)
        └── auth → rate-limiter → circuit-breaker → ...
    ↓
HTTP/WebSocket/gRPC Proxy
    ↓
Response (with metrics & traces recorded)
```

### GatewayContext

The `GatewayContext` object carries per-request state through the pipeline. Plugins should use it to share auth info, upstream info, and custom metadata:

```python
ctx.request_id      # UUID string
ctx.route_id        # Matched route id
ctx.auth_method     # "jwt" | "api_key" | "mtls"
ctx.principal       # Authenticated user/key identifier
ctx.scopes          # List of authorized scopes
ctx.claims          # JWT claims dict
ctx.circuit_open    # Boolean circuit breaker state
ctx.metadata        # dict for custom plugin data
```

---

## Built-in Plugins Reference

| Plugin name | Config keys | Notes |
|---|---|---|
| `request-id` | — | Injects `X-Request-ID`; global, runs first |
| `access-logger` | `log_headers`, `log_body` | Structured JSON access log |
| `jwt-validator` | `secret_key`, `algorithm`, `jwks_url`, `audience`, `issuer` | HMAC & RSA; JWKS auto-fetch |
| `api-key` | `keys[]`, `header_name`, `query_param` | Static key list |
| `mtls-enforcer` | `allowed_dns[]` | Validates `X-Client-Cert` header |
| `rate-limiter` | `limit`, `window`, `key_func` | Redis Token Bucket (Lua atomic) |
| `circuit-breaker` | `failure_threshold`, `recovery_timeout`, `success_threshold`, `window_seconds` | Distributed via Redis |

---

## Admin API

Base URL: `http://localhost:9000` — All requests except `/_health` require `X-Admin-Key` header.

| Method | Path | Description |
|---|---|---|
| `GET` | `/_health` | Health check (no auth) |
| `GET` | `/api/v1/routes` | List all routes |
| `GET` | `/api/v1/routes/{id}` | Get route by ID |
| `POST` | `/api/v1/reload` | Hot-reload config from files |
| `GET` | `/api/v1/plugins` | List registered plugins |

---

## Observability

### Prometheus Metrics (endpoint: `GET /metrics`)

| Metric | Type | Description |
|---|---|---|
| `gateway_requests_total` | Counter | Total proxied requests by route, method, status |
| `gateway_request_duration_seconds` | Histogram | Request latency |
| `gateway_active_connections` | Gauge | Current active connections |
| `gateway_circuit_breaker_open` | Gauge | CB state per route (0/1) |
| `gateway_auth_failures_total` | Counter | Auth failure count by method |

### Structured Logging

All logs are JSON by default. Key fields:
- `request_id`, `route_id`, `method`, `path`, `status_code`, `duration_ms`
- `auth_method`, `principal`

### OpenTelemetry Tracing

Set `OBSERVABILITY__OTEL_EXPORTER_ENDPOINT` to a Jaeger/Zipkin/OTLP-compatible endpoint. FastAPI auto-instrumentation is enabled via `opentelemetry-instrumentation-fastapi`.

---

## Testing

### Load Testing (k6)

```bash
# Install k6 first
cd apigw
k6 run tests/load/rest_load_test.js

# Custom VUs / duration
k6 run --vus 100 --duration 60s tests/load/rest_load_test.js
```

Set `BASE_URL` env var to target a non-default host:

```bash
BASE_URL=http://my-gateway:8080 k6 run tests/load/rest_load_test.js
```

### Linting & Type Checking

```bash
cd apigw
ruff check .          # Linting (line-length: 100, Python 3.11)
mypy gateway admin    # Strict type checking
```

---

## Kubernetes Deployment

```bash
cd apigw/deployments/kubernetes

# Apply all manifests
kubectl apply -f base/

# Check status
kubectl -n oag-system get pods

# Port-forward gateway
kubectl -n oag-system port-forward svc/gateway 8080:8080
```

Manifests:
- `00-namespace.yaml` → `oag-system` namespace
- `01-configmap.yaml` → routes.yaml + gateway.yaml
- `02-redis.yaml` → Redis StatefulSet
- `03-mock.yaml` → Mock upstream
- `04-gateway.yaml` → Gateway Deployment + Service
- `05-admin.yaml` → Admin Deployment + Service
- `06-hpa.yaml` → HPA (CPU 70%, 1–5 replicas)
- `07-pdb.yaml` → PodDisruptionBudget (minAvailable: 1)

To update config in K8s, edit the ConfigMap in `01-configmap.yaml` and call the Admin reload endpoint — no pod restart required.

---

## Architecture Notes

- **Async-first:** All I/O uses `asyncio`; HTTP client is `httpx.AsyncClient` with a shared connection pool.
- **No proto compilation required for gRPC proxy:** The generic gRPC handler reflects upstream schemas at runtime.
- **Distributed state via Redis:** Rate limiter uses atomic Lua scripts; circuit breaker stores state in Redis keys (`cb:open:{route_id}`, `cb:fails:{route_id}`).
- **Plugin ordering:** Plugins run in ascending `order` value. Global plugins wrap all per-route plugins.
- **Config reload:** Thread-safe via `asyncio.Lock` in `ConfigLoader`. File watcher polls every 5 seconds; K8s ConfigMap updates are detected automatically.
- **Graceful shutdown:** PreStop hook adds a 10s delay; in-flight requests complete before process exits.
- **Multi-worker:** Uses Gunicorn + UvicornWorker. Redis coordinates shared state across workers.

---

## Common Pitfalls

1. **Plugin not loading:** Ensure the plugin module is imported somewhere in `app.py` so `PluginRegistry.register()` is called.
2. **Route not matching:** Routes are first-match-wins. If a broad route is defined before a specific one, the specific route will never be reached — reorder accordingly.
3. **Redis unavailable:** Health check (`/_health`) will fail. Rate limiter and circuit breaker will raise errors if Redis is unreachable.
4. **gRPC reflection errors:** The gRPC listener requires server reflection to be enabled on the upstream for the generic proxy to work.
5. **Config reload not propagating:** In multi-worker mode, use the Admin `/api/v1/reload` endpoint which broadcasts via Redis Pub/Sub to all workers.
6. **mTLS header injection:** The `mtls-enforcer` plugin expects `X-Client-Cert` to be injected by the TLS termination layer (e.g., Nginx, Envoy). It does not perform TLS termination itself.
