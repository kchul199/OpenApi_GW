# 테스트 가이드 — Open API Gateway

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [환경 설정](#2-환경-설정)
3. [단위 테스트 실행](#3-단위-테스트-실행)
4. [테스트 파일 구조 및 항목](#4-테스트-파일-구조-및-항목)
5. [커버리지 리포트](#5-커버리지-리포트)
6. [린트 및 타입 체크](#6-린트-및-타입-체크)
7. [통합 테스트 (Docker)](#7-통합-테스트-docker)
8. [부하 테스트 (k6)](#8-부하-테스트-k6)
9. [자주 발생하는 오류 해결](#9-자주-발생하는-오류-해결)
10. [CI 파이프라인 참고](#10-ci-파이프라인-참고)

---

## 1. 사전 요구사항

| 도구 | 최소 버전 | 확인 명령 |
|---|---|---|
| Python | 3.11 | `python --version` |
| pip | 23+ | `pip --version` |
| Docker (통합/부하 테스트) | 24+ | `docker --version` |
| k6 (부하 테스트) | 0.50+ | `k6 version` |

---

## 2. 환경 설정

### 2-1. 가상환경 생성 및 패키지 설치

```bash
# 프로젝트 루트로 이동
cd apigw

# 가상환경 생성
python -m venv .venv

# 활성화 — macOS / Linux
source .venv/bin/activate

# 활성화 — Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 2-2. 설치 확인

```bash
python -c "import fastapi, pytest, httpx, jose, redis; print('OK')"
```

---

## 3. 단위 테스트 실행

> 단위 테스트는 Redis·Docker 없이 실행됩니다. 모든 외부 의존성은 `unittest.mock`으로 처리합니다.

### 전체 실행

```bash
pytest tests/unit/ -v
```

### 파일별 실행

```bash
# 라우터 테스트 (33개)
pytest tests/unit/test_router.py -v

# 파이프라인 테스트 (9개)
pytest tests/unit/test_pipeline.py -v

# 플러그인 테스트 (23개)
pytest tests/unit/test_plugins.py -v

# 프록시 테스트 (17개)
pytest tests/unit/test_proxy.py -v
```

### 클래스 / 함수 단위 실행

```bash
# JWT 플러그인 테스트만
pytest tests/unit/test_plugins.py::TestJWTPlugin -v

# 특정 테스트 하나
pytest tests/unit/test_router.py::TestRoutingEngineMatch::test_wrong_method_no_match -v
```

### 자주 쓰는 옵션

| 옵션 | 설명 |
|---|---|
| `-v` | 테스트 이름 상세 출력 |
| `-q` | 간소화 출력 (실패만) |
| `-s` | `print()` 출력 허용 |
| `--lf` | 마지막 실패 테스트만 재실행 |
| `-x` | 첫 번째 실패 시 즉시 중단 |
| `-k "jwt"` | 이름에 "jwt"가 포함된 테스트만 실행 |
| `--tb=short` | 짧은 트레이스백 출력 |

```bash
# 예시: JWT 관련 테스트만 빠르게 재실행
pytest tests/unit/ -k "jwt" --lf -v

# 예시: 첫 실패에서 멈추고 상세 출력
pytest tests/unit/ -x -s
```

---

## 4. 테스트 파일 구조 및 항목

```
tests/
├── unit/
│   ├── conftest.py          # 공통 픽스처 (make_request, make_route, ctx)
│   ├── test_router.py       # 라우팅 엔진
│   ├── test_pipeline.py     # 미들웨어 파이프라인
│   ├── test_plugins.py      # 인증·레이트리밋·서킷브레이커 플러그인
│   └── test_proxy.py        # HTTP 리버스 프록시
└── load/
    └── rest_load_test.js    # k6 부하 테스트 (§8 참조)
```

### test_router.py — 33개

`_match_path`, `_match_headers`, `RoutingEngine` 라우팅 로직을 검증합니다.

| 클래스 | 검증 항목 |
|---|---|
| `TestMatchPath` | 정확 일치 / glob prefix (`/api/**`) / 정규식 (`~/v[0-9]+`) / 불일치 |
| `TestMatchHeaders` | 헤더 조건 전체 일치 / 키 누락 / 값 불일치 |
| `TestRoutingEngineMatch` | HTTP 경로·메서드·호스트·헤더 조건 매칭, 첫 번째 매칭 우선, 프로토콜 미스매치 |
| `TestMatchGrpc` | gRPC 경로 매칭, HTTP 라우트 혼입 방지, 호스트 필터 |
| `TestResolveUpstream` | round_robin / ip_hash 고정성 / 다수 IP 분산 / 타겟 없음 / 프로토콜 설정 |

```
tests/unit/test_router.py::TestMatchPath::test_exact_match
tests/unit/test_router.py::TestMatchPath::test_exact_no_match
tests/unit/test_router.py::TestMatchPath::test_prefix_glob_match
tests/unit/test_router.py::TestMatchPath::test_prefix_glob_root_match
tests/unit/test_router.py::TestMatchPath::test_prefix_glob_no_match
tests/unit/test_router.py::TestMatchPath::test_single_wildcard
tests/unit/test_router.py::TestMatchPath::test_regex_match
tests/unit/test_router.py::TestMatchPath::test_regex_no_match
tests/unit/test_router.py::TestMatchPath::test_regex_fullmatch_required
tests/unit/test_router.py::TestMatchHeaders::test_all_required_headers_present
tests/unit/test_router.py::TestMatchHeaders::test_missing_required_header
tests/unit/test_router.py::TestMatchHeaders::test_wrong_header_value
tests/unit/test_router.py::TestMatchHeaders::test_empty_required_always_passes
tests/unit/test_router.py::TestRoutingEngineMatch::test_exact_path_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_prefix_path_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_wrong_method_no_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_host_filter_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_host_filter_no_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_header_condition_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_header_condition_no_match
tests/unit/test_router.py::TestRoutingEngineMatch::test_first_route_wins
tests/unit/test_router.py::TestRoutingEngineMatch::test_no_routes_returns_none
tests/unit/test_router.py::TestRoutingEngineMatch::test_protocol_mismatch_skipped
tests/unit/test_router.py::TestRoutingEngineMatch::test_update_routes_replaces_table
tests/unit/test_router.py::TestMatchGrpc::test_grpc_path_match
tests/unit/test_router.py::TestMatchGrpc::test_grpc_no_match
tests/unit/test_router.py::TestMatchGrpc::test_grpc_http_route_not_returned
tests/unit/test_router.py::TestMatchGrpc::test_grpc_host_filter
tests/unit/test_router.py::TestResolveUpstream::test_round_robin_returns_upstream
tests/unit/test_router.py::TestResolveUpstream::test_ip_hash_is_sticky
tests/unit/test_router.py::TestResolveUpstream::test_ip_hash_different_ips_may_differ
tests/unit/test_router.py::TestResolveUpstream::test_empty_targets_returns_none
tests/unit/test_router.py::TestResolveUpstream::test_upstream_protocol_is_set
```

---

### test_pipeline.py — 9개

Chain of Responsibility 패턴의 실행 순서와 예외 동작을 검증합니다.

| 클래스 | 검증 항목 |
|---|---|
| `TestBuildChain` | 단일 플러그인 → 핸들러 순서 / 복수 플러그인 정렬 / 빈 체인 / short-circuit |
| `TestMiddlewarePipeline` | global + route 플러그인 통합 실행 / disabled 스킵 / 미등록 이름 스킵 / 핸들러 응답 반환 |

```
tests/unit/test_pipeline.py::TestBuildChain::test_single_plugin_then_handler
tests/unit/test_pipeline.py::TestBuildChain::test_plugins_execute_in_order
tests/unit/test_pipeline.py::TestBuildChain::test_empty_plugin_list_calls_handler
tests/unit/test_pipeline.py::TestBuildChain::test_short_circuit_prevents_handler
tests/unit/test_pipeline.py::TestMiddlewarePipeline::test_global_plugins_run_before_route_plugins
tests/unit/test_pipeline.py::TestMiddlewarePipeline::test_disabled_plugin_is_skipped
tests/unit/test_pipeline.py::TestMiddlewarePipeline::test_unknown_plugin_name_is_skipped
tests/unit/test_pipeline.py::TestMiddlewarePipeline::test_pipeline_returns_proxy_handler_response
tests/unit/test_pipeline.py::TestMiddlewarePipeline::test_short_circuit_plugin_blocks_handler
```

---

### test_plugins.py — 23개

Redis는 `AsyncMock`으로, JWKS는 `patch`로 처리합니다.

| 클래스 | 검증 항목 |
|---|---|
| `TestJWTPlugin` | 유효 토큰 통과 / 헤더 없음 401 / 서명 오류 401 / 만료 401 / 에러 정보 미노출 / JWKS 실패 401 / scope 파싱 |
| `TestAPIKeyPlugin` | 키 누락 → **401** / 잘못된 키 → **403** / 헤더 인증 / 쿼리파람 인증 / principal 설정 |
| `TestRateLimiterPlugin` | Redis 허용 → 200 / Redis 차단 → 429 / Retry-After 헤더 / Redis 장애 → **fail open** / SHA 캐시 재사용 |
| `TestCircuitBreakerPlugin` | CLOSED 통과 / OPEN → 503 / OPEN 컨텍스트 플래그 / 5xx → 실패 카운트 / 2xx → 카운트 없음 / 임계치 도달 → 차단 |

```
tests/unit/test_plugins.py::TestJWTPlugin::test_valid_token_passes
tests/unit/test_plugins.py::TestJWTPlugin::test_missing_header_returns_401
tests/unit/test_plugins.py::TestJWTPlugin::test_invalid_signature_returns_401
tests/unit/test_plugins.py::TestJWTPlugin::test_expired_token_returns_401
tests/unit/test_plugins.py::TestJWTPlugin::test_error_message_does_not_leak_details
tests/unit/test_plugins.py::TestJWTPlugin::test_jwks_fetch_failure_returns_401
tests/unit/test_plugins.py::TestJWTPlugin::test_scope_parsed_as_space_separated_list
tests/unit/test_plugins.py::TestAPIKeyPlugin::test_missing_key_returns_401
tests/unit/test_plugins.py::TestAPIKeyPlugin::test_invalid_key_returns_403
tests/unit/test_plugins.py::TestAPIKeyPlugin::test_valid_key_via_header_passes
tests/unit/test_plugins.py::TestAPIKeyPlugin::test_valid_key_via_query_param_passes
tests/unit/test_plugins.py::TestAPIKeyPlugin::test_principal_is_truncated_key
tests/unit/test_plugins.py::TestRateLimiterPlugin::test_allowed_request_passes_through
tests/unit/test_plugins.py::TestRateLimiterPlugin::test_blocked_request_returns_429
tests/unit/test_plugins.py::TestRateLimiterPlugin::test_retry_after_header_present_on_429
tests/unit/test_plugins.py::TestRateLimiterPlugin::test_redis_failure_fails_open
tests/unit/test_plugins.py::TestRateLimiterPlugin::test_script_sha_cached_across_calls
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_closed_circuit_passes_request
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_open_circuit_returns_503
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_open_circuit_sets_context_flag
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_5xx_response_records_failure
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_2xx_response_does_not_record_failure
tests/unit/test_plugins.py::TestCircuitBreakerPlugin::test_trips_circuit_when_threshold_reached
```

---

### test_proxy.py — 17개

`pytest-httpx`의 `httpx_mock` 픽스처로 upstream HTTP 응답을 모킹합니다.

| 클래스 | 검증 항목 |
|---|---|
| `TestFilterHeaders` | hop-by-hop 헤더 전체 제거 / 안전 헤더 보존 / 빈 딕셔너리 / 대소문자 |
| `TestBuildUrl` | 단순 경로 전달 / `strip_prefix` 제거 / 루트 → `/` / 쿼리스트링 추가 / base URL 슬래시 정규화 |
| `TestHTTPReverseProxy` | 성공 200 / X-Request-ID 응답 헤더 / 타임아웃 → 504 / 연결 오류 → 502 / upstream 미설정 → 502 / 미초기화 → 503 / hop-by-hop 필터 / 502 재시도 |

```
tests/unit/test_proxy.py::TestFilterHeaders::test_removes_all_hop_by_hop_headers
tests/unit/test_proxy.py::TestFilterHeaders::test_preserves_safe_headers
tests/unit/test_proxy.py::TestFilterHeaders::test_empty_headers
tests/unit/test_proxy.py::TestFilterHeaders::test_case_sensitive_hop_by_hop_removal
tests/unit/test_proxy.py::TestBuildUrl::test_simple_path_forwarding
tests/unit/test_proxy.py::TestBuildUrl::test_strip_prefix_removes_path_prefix
tests/unit/test_proxy.py::TestBuildUrl::test_strip_prefix_root_becomes_slash
tests/unit/test_proxy.py::TestBuildUrl::test_query_string_appended
tests/unit/test_proxy.py::TestBuildUrl::test_trailing_slash_in_base_trimmed
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_successful_proxy
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_request_id_forwarded_in_response
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_upstream_timeout_returns_504
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_upstream_connect_error_returns_502
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_no_upstream_returns_502
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_proxy_not_initialized_returns_503
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_hop_by_hop_headers_not_forwarded
tests/unit/test_proxy.py::TestHTTPReverseProxy::test_retry_on_502_status
```

---

## 5. 커버리지 리포트

```bash
# pytest-cov 설치 (최초 1회)
pip install pytest-cov

# 터미널 출력 (미커버 라인 표시)
pytest tests/unit/ --cov=gateway --cov-report=term-missing

# HTML 리포트 생성 (브라우저에서 확인)
pytest tests/unit/ --cov=gateway --cov-report=html
open htmlcov/index.html        # macOS
start htmlcov/index.html       # Windows
```

예상 커버리지 (주요 모듈):

| 모듈 | 예상 커버리지 |
|---|---|
| `gateway/core/router.py` | ~95% |
| `gateway/core/pipeline.py` | ~95% |
| `gateway/core/proxy.py` | ~85% |
| `gateway/plugins/auth/jwt_plugin.py` | ~100% |
| `gateway/plugins/auth/apikey_plugin.py` | ~100% |
| `gateway/plugins/ratelimit/ratelimit_plugin.py` | ~90% |
| `gateway/plugins/circuitbreaker/breaker_plugin.py` | ~90% |

---

## 6. 린트 및 타입 체크

```bash
# 코드 스타일 검사 (ruff)
ruff check gateway/ tests/

# 자동 수정
ruff check gateway/ tests/ --fix

# 타입 체크 (mypy)
mypy gateway/
```

---

## 7. 통합 테스트 (Docker)

실제 Redis와 게이트웨이를 띄운 상태에서 수동으로 엔드포인트를 검증합니다.

### 서비스 시작

```bash
docker compose -f deployments/docker-compose.yaml up -d redis gateway admin
```

### 헬스 체크

```bash
# 게이트웨이 헬스
curl http://localhost:8080/_health

# 응답 예시
# {"status":"ok","routes":3,"redis":"ok"}
```

### API Key 인증 테스트

```bash
# 키 없음 → 401
curl -i http://localhost:8080/api/v1/test

# 잘못된 키 → 403
curl -i -H "X-API-Key: wrong-key" http://localhost:8080/api/v1/test

# 유효한 키 → 200
curl -i -H "X-API-Key: your-api-key" http://localhost:8080/api/v1/test
```

### JWT 인증 테스트

```bash
# 토큰 발급 (예시 — 실제 secret_key는 config/routes.yaml 참조)
TOKEN=$(python -c "
from jose import jwt
print(jwt.encode({'sub':'user1','scope':'read write'}, 'changeme', algorithm='HS256'))
")

curl -i -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/users
```

### Rate Limiter 테스트

```bash
# 동일 IP로 연속 요청 → 일정 횟수 후 429
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/test
done
```

### Config Hot-Reload 테스트

```bash
# Admin API로 즉시 리로드
curl -X POST http://localhost:9000/api/v1/reload \
     -H "X-Admin-Key: changeme-admin-key"

# 응답 예시
# {"status":"reloaded","routes":3}
```

### 서비스 종료

```bash
docker compose -f deployments/docker-compose.yaml down
```

---

## 8. 부하 테스트 (k6)

### k6 설치

```bash
# macOS
brew install k6

# Ubuntu/Debian
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# Windows (Chocolatey)
choco install k6
```

### 서비스 실행 후 테스트

```bash
# 1. 먼저 서비스 시작
docker compose -f deployments/docker-compose.yaml up -d

# 2. 부하 테스트 실행
k6 run tests/load/rest_load_test.js

# 3. 가상 유저 수 / 지속 시간 지정
k6 run --vus 50 --duration 30s tests/load/rest_load_test.js
```

---

## 9. 자주 발생하는 오류 해결

### `ModuleNotFoundError: No module named 'gateway'`

프로젝트 루트(`apigw/`)에서 실행하고 있는지 확인합니다.

```bash
pwd          # /path/to/apigw 여야 함
pytest tests/unit/ -v
```

### `RuntimeError: no running event loop`

`pyproject.toml`에 `asyncio_mode = "auto"` 설정이 있으므로 자동 처리됩니다.
오류가 지속되면 `pytest-asyncio`를 업데이트합니다.

```bash
pip install "pytest-asyncio>=0.23" --upgrade
```

### `ImportError: cannot import name 'HTTPXMock'`

`pytest-httpx` 버전을 확인합니다.

```bash
pip install "pytest-httpx>=0.30" --upgrade
```

### `jose.exceptions.JWKError` (JWT 테스트)

`python-jose[cryptography]`가 설치되었는지 확인합니다.

```bash
pip install "python-jose[cryptography]"
```

### gRPC 관련 `ImportError`

시스템 SSL 라이브러리가 필요합니다.

```bash
# macOS
brew install openssl

# Ubuntu/Debian
sudo apt-get install -y libssl-dev gcc
pip install grpcio --no-binary grpcio
```

### Redis 연결 오류 (통합 테스트)

단위 테스트는 Redis가 필요 없습니다. 통합 테스트 실행 전 Redis가 동작 중인지 확인합니다.

```bash
docker compose -f deployments/docker-compose.yaml up -d redis
redis-cli ping   # PONG 응답 확인
```

---

## 10. CI 파이프라인 참고

로컬에서 CI와 동일한 순서로 전체 품질 검사를 실행하려면:

```bash
# 1. 린트
ruff check gateway/ tests/

# 2. 타입 체크
mypy gateway/

# 3. 단위 테스트 + 커버리지
pytest tests/unit/ --cov=gateway --cov-report=term-missing -q

# 한 줄로 전부 실행
ruff check gateway/ tests/ && mypy gateway/ && pytest tests/unit/ -q
```

성공 시 출력 예시:

```
82 passed in 3.41s
```
