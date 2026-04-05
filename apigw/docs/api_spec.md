# Open API Gateway 연동 및 규격서

## 1. 시스템 인터페이스 개요

Open API Gateway는 백엔드 인프라를 외부로 노출하는 진입점 역할을 수행합니다. 포트는 역할에 따라 수직 분리하여 운영합니다.

| 포트 | 역할 | 프로토콜 |
|---|---|---|
| `8080` | 서비스 트래픽 (HTTP / WebSocket) | HTTP/1.1, WS |
| `9090` | 서비스 트래픽 (gRPC) | HTTP/2 |
| `9000` | 어드민 관리 API | HTTP/1.1 |

---

## 2. 라우팅 룰(Route Rule) 정의 규격

모든 라우팅 규칙은 K8s ConfigMap 또는 `config/routes.yaml`을 통해 선언적으로 제어됩니다.

```yaml
# config/routes.yaml 전체 구조
routes:
  - id: "payment-service-v1"            # 라우트 고유 식별자 (필수)
    description: "Payment service v1"   # 설명 (선택)
    match:
      protocol: HTTP                    # HTTP | gRPC | WebSocket (필수)
      path: "/api/v1/payments/**"       # 경로 패턴 (필수)
      methods: [POST, GET]              # HTTP 메서드 목록 (gRPC·WebSocket은 무시)
      host: null                        # Host 헤더 조건 (선택)
      headers: {}                       # 추가 헤더 조건 key:value (선택)
    upstream:
      type: REST                        # REST | gRPC | WebSocket (필수)
      targets:                          # 업스트림 서버 목록 (1개 이상 필수)
        - url: "http://payment-svc.default.svc.cluster.local:8080"
          weight: 100                   # 로드밸런싱 가중치 (1~100)
      timeout: 3.0                      # 업스트림 응답 타임아웃 (초, 기본: 30.0)
      retry:
        count: 3                        # 재시도 횟수 (기본: 3)
        backoff_factor: 0.5             # 지수 백오프 계수 (기본: 0.3)
        status_codes: [502, 503, 504]   # 재시도 대상 HTTP 상태 코드
      load_balance: round_robin         # round_robin | random | ip_hash
    strip_prefix: true                  # 업스트림 전달 시 경로 접두사 제거 여부
    preserve_host: false                # 원본 Host 헤더 유지 여부
    plugins:                            # 라우트별 플러그인 목록 (선택)
      - name: rate-limiter              # 플러그인 등록명 (하이픈 구분, 소문자)
        enabled: true
        config:
          limit: 100
          window: 60
          key_func: ip
      - name: jwt-validator
        enabled: true
        config:
          jwks_url: "https://auth.example.com/.well-known/jwks.json"
          algorithm: RS256
```

### 필수 항목 사양

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `id` | string | ✅ | — | 라우트 고유 식별자. 로깅·트레이싱 TraceSpan 핵심 키 |
| `match.protocol` | string | ✅ | — | `HTTP` \| `gRPC` \| `WebSocket` |
| `match.path` | string | ✅ | — | 경로 패턴. `**` 와일드카드, `~` 정규식 접두사 지원 |
| `match.methods` | list | — | 전체 | HTTP 메서드 목록 |
| `upstream.targets` | list | ✅ | — | 업스트림 서버. 각 항목에 `url`과 `weight` 필요 |
| `upstream.timeout` | float | — | `30.0` | 업스트림 응답 타임아웃 (초) |
| `upstream.load_balance` | string | — | `round_robin` | `round_robin` \| `random` \| `ip_hash` |
| `strip_prefix` | bool | — | `false` | 업스트림 전달 경로에서 매칭된 접두사 제거 |
| `preserve_host` | bool | — | `false` | 원본 `Host` 헤더 유지 |

---

## 3. 전역 게이트웨이 설정 규격 (gateway.yaml)

`config/gateway.yaml`에서 모든 라우트에 공통 적용되는 전역 플러그인을 선언합니다.

```yaml
# config/gateway.yaml
name: Open API Gateway
version: "1.0.0"

global_plugins:
  - name: request-id
    enabled: true
    config: {}

  - name: access-logger
    enabled: true
    config:
      log_headers: false
      log_body: false
```

---

## 4. 내장 플러그인 (Plugins) 규격

플러그인은 **전역(Global)** 과 **라우트별(Per-route)** 두 계층으로 구분됩니다. 전역 플러그인이 먼저 실행됩니다.

> **플러그인 이름 규칙:** 모두 소문자 하이픈 구분(`kebab-case`)을 사용합니다. `routes.yaml`의 `name` 필드에 정확히 일치해야 합니다.

---

### 4.1 전역 플러그인 (Global Plugins)

#### `request-id` — 요청 ID 주입
- **실행 순서(order):** 1
- **기능:** 모든 요청에 고유한 UUID v4를 `X-Request-ID` 헤더로 부여합니다. 클라이언트가 헤더를 이미 제공하면 재사용합니다. 이후 모든 플러그인과 프록시 응답에 전파됩니다.
- **설정 키:** 없음
- **응답 헤더:** `X-Request-ID: <uuid>`

---

#### `access-logger` — 구조화 액세스 로그
- **실행 순서(order):** 2
- **기능:** 요청·응답 정보를 JSON 포맷으로 기록합니다. `orjson` 기반 고속 직렬화를 사용합니다.
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `log_headers` | bool | `false` | 요청 헤더 전체를 로그에 포함할지 여부 |
| `log_body` | bool | `false` | 요청 바디 스니펫을 로그에 포함할지 여부 |

- **로그 포함 필드:** `request_id`, `method`, `path`, `remote_addr`, `status`, `duration_ms`, `route_id`, `principal`

---

### 4.2 인증 플러그인 (Auth Plugins)

#### `mtls-enforcer` — mTLS 클라이언트 인증서 검증
- **실행 순서(order):** 5
- **기능:** 엣지 로드밸런서(Envoy, Nginx, AWS ALB 등)가 TLS Termination 후 주입한 클라이언트 인증서 헤더를 검사하여 상호 인증(mTLS)을 강제합니다.
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `cert_header` | string | `x-client-cert` | 엣지 LB가 인증서 정보를 담아 전달하는 헤더명 |
| `allowed_subjects` | list | `[]` | 허용할 Subject DN 목록. 비어있으면 헤더 존재 여부만 확인 |

- **응답:** 인증서 헤더 없음 → `401 Unauthorized` / Subject DN 불일치 → `403 Forbidden`
- **컨텍스트 주입:** `ctx.auth_method = MTLS`, `ctx.principal = <cert 앞 50자>`

---

#### `jwt-validator` — JWT 토큰 검증
- **실행 순서(order):** 10
- **기능:** `Authorization: Bearer <token>` 헤더를 파싱하여 서명 및 클레임을 검증합니다. `jwks_url` 설정 시 Auth0·Keycloak 등 외부 IdP에서 공개 키를 동적으로 조회합니다.
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `secret_key` | string | `changeme` | HMAC 시크릿(HS256) 또는 PEM 공개키(RS256). **운영 환경에서는 반드시 K8s Secret으로 주입** |
| `jwks_url` | string | `""` | JWKS 엔드포인트 URL. 설정 시 동적 공개키 조회 활성화 (`secret_key` 무시) |
| `algorithm` | string | `HS256` | 서명 알고리즘: `HS256` \| `RS256` \| `ES256` |
| `audience` | string | `null` | 검증할 `aud` 클레임 (선택) |
| `issuer` | string | `null` | 검증할 `iss` 클레임 (선택) |

- **응답:** 토큰 없음·검증 실패 → `401 Unauthorized` (헤더: `WWW-Authenticate: Bearer`)
- **컨텍스트 주입:** `ctx.auth_method = JWT`, `ctx.principal = <sub 클레임>`, `ctx.scopes`, `ctx.claims`

---

#### `api-key` — API 키 검증
- **실행 순서(order):** 11
- **기능:** `x-api-key` 헤더(또는 지정 쿼리 파라미터)를 검사하여 등록된 키 목록과 대조합니다.
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `keys` | list | `[]` | 유효한 API 키 문자열 목록. **운영 환경에서는 K8s Secret으로 주입** |
| `header_name` | string | `x-api-key` | API 키를 읽을 요청 헤더명 |
| `query_param` | string | `null` | 헤더 대체 쿼리 파라미터명 (선택) |

- **응답:**
  - 키 없음 → `401 Unauthorized`
  - 키 불일치 → `403 Forbidden`
- **컨텍스트 주입:** `ctx.auth_method = API_KEY`, `ctx.principal = "apikey:<앞8자>…"`

---

### 4.3 트래픽 제어 플러그인 (Traffic Control Plugins)

#### `rate-limiter` — 분산 요청 속도 제한
- **실행 순서(order):** 20
- **기능:** Redis Lua 스크립트 기반 **Token Bucket** 알고리즘으로 분산 환경에서도 정확한 요청 속도 제한을 보장합니다. 모든 Gateway Pod가 동일한 Redis 카운터를 공유하므로 스케일아웃 시에도 일관성이 유지됩니다.
- **Redis 키:** `ratelimit:ip:<ip>` | `ratelimit:user:<principal>` | `ratelimit:apikey:<principal>`
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `limit` | int | `100` | 윈도우(`window`)당 최대 허용 요청 수 (Token Bucket 용량) |
| `window` | int | `60` | 윈도우 크기 (초). 리필 속도 = `limit / window` 토큰/초 |
| `key_func` | string | `ip` | 제한 기준: `ip` (X-Forwarded-For) \| `user` (JWT sub) \| `api_key` |

- **응답:** 초과 시 `429 Too Many Requests`
- **응답 헤더:** `Retry-After: <window초>`, `X-RateLimit-Limit: <limit>`
- **Redis 장애 정책:** Fail-open (Redis 연결 실패 시 트래픽 통과 허용 후 에러 로그)

---

#### `circuit-breaker` — 분산 서킷 브레이커
- **실행 순서(order):** 25
- **기능:** 업스트림 연속 실패 횟수가 임계치를 초과하면 Circuit을 Open 상태로 전환하여 Cascading Failure를 방지합니다. Redis 기반 분산 상태 관리로 모든 Pod에 장애 상태가 즉각 전파됩니다.
- **상태 전이:** `CLOSED` → (연속 실패 `failure_threshold`회 초과) → `OPEN` → (`recovery_timeout`초 경과, Redis TTL 소멸) → `CLOSED`
- **Redis 키:**
  - `cb:open:{route_id}` — Circuit Open 플래그 (TTL = recovery_timeout)
  - `cb:fails:{route_id}` — 연속 실패 카운터 (TTL = window_seconds)
- **설정 키:**

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `failure_threshold` | int | `5` | Circuit 오픈 트리거 연속 실패 **횟수** (비율 아님) |
| `recovery_timeout` | float | `30.0` | Circuit Open 유지 시간 (초). 경과 후 자동 복구 |
| `window_seconds` | int | `60` | 실패 카운터 유효 윈도우 (초) |

- **응답:** Circuit Open → `503 Service Unavailable`
- **응답 헤더:** `Retry-After: <남은TTL초>`

---

## 5. 시스템 엔드포인트 규격

### 5.1 게이트웨이 시스템 엔드포인트 (포트 8080, 인증 불필요)

#### `GET /_health` — Liveness Probe

K8s Liveness Probe 및 외부 모니터링 도구에서 호출합니다. Redis 연결 상태를 실시간으로 점검합니다.

- **정상 응답 (200 OK):**
```json
{
  "status": "ok",
  "routes": 12,
  "redis": "ok"
}
```
- **이상 응답 (503 Service Unavailable):** Redis 연결 실패 시
```json
{
  "status": "error",
  "reason": "redis_unavailable"
}
```

---

#### `GET /_ready` — Readiness Probe

K8s Readiness Probe용 엔드포인트. 파드가 트래픽 수신 준비가 된 경우 200을 반환합니다.

- **응답 (200 OK):**
```json
{
  "status": "ready"
}
```

---

### 5.2 어드민 API 엔드포인트 (포트 9000)

모든 Admin API 요청은 다음 중 하나로 인증이 필요합니다.
- **헤더:** `X-Admin-Key: <api_key>`
- **쿼리 파라미터:** `?_key=<api_key>`

> **보안 주의:** Admin API 포트(9000)는 ClusterIP 서비스로 내부 네트워크에서만 접근 가능하도록 반드시 제한하십시오. `ADMIN__API_KEY` 환경변수로 기본값(`changeme-admin-key`)을 반드시 변경하십시오.

---

#### `POST /api/v1/reload` — 라우트 핫-리로드

`routes.yaml`을 재로드하고 Redis Pub/Sub(`oag:config_reload` 채널)으로 전체 Gateway Pod에 브로드캐스트합니다.

- **응답 (200 OK):**
```json
{
  "status": "reloaded",
  "routes": 12
}
```
- **응답 (401 Unauthorized):** 인증 키 없음 또는 불일치

---

#### `GET /api/v1/routes` — 라우트 목록 조회

현재 로드된 모든 라우트 요약 목록을 반환합니다.

- **응답 (200 OK):**
```json
{
  "routes": [
    {
      "id": "user-service-v1",
      "description": "User management service v1",
      "protocol": "HTTP",
      "path": "/api/v1/users/**",
      "upstream_count": 2
    }
  ],
  "total": 1
}
```

---

#### `GET /api/v1/routes/{route_id}` — 라우트 개별 조회

특정 라우트의 전체 설정을 반환합니다.

- **응답 (200 OK):** RouteConfig 전체 객체
- **응답 (404 Not Found):** 해당 route_id 없음

---

#### `GET /api/v1/plugins` — 등록 플러그인 목록 조회

현재 게이트웨이에 등록된 플러그인 이름 목록을 반환합니다.

- **응답 (200 OK):**
```json
{
  "plugins": [
    "access-logger",
    "api-key",
    "circuit-breaker",
    "jwt-validator",
    "mtls-enforcer",
    "rate-limiter",
    "request-id"
  ]
}
```

---

#### `GET /api/v1/health` — Admin 서버 헬스체크

Admin 서버 및 설정 상태를 점검합니다. **인증 불필요.**

- **응답 (200 OK):**
```json
{
  "status": "ok",
  "routes_loaded": 12
}
```
