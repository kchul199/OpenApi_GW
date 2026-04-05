# Open API Gateway (OAG)

Open API Gateway는 FastAPI 기반의 멀티 프로토콜 API 게이트웨이입니다.  
HTTP/REST, WebSocket, gRPC 트래픽을 단일 게이트웨이 계층에서 라우팅하고, 플러그인 방식으로 인증/레이트리밋/서킷브레이커/로깅을 적용할 수 있습니다.

## 프로젝트 개요

- 목적: 마이크로서비스 환경에서 API 경계(Edge) 계층을 표준화
- 핵심 가치: 멀티 프로토콜, 플러그인 확장성, 운영 가시성, 런타임 라우트 관리
- 운영 모델: Redis 기반 상태 공유 + Admin Control Plane + Observability 지표

## 상세 설명

### 1) 데이터 플레인 (Gateway)

- HTTP/REST, WebSocket, gRPC 요청을 수신
- `config/routes.yaml` 규칙으로 라우팅
- 글로벌/라우트 플러그인을 체인으로 실행
- 업스트림 선택 전략 지원
  - `round_robin`
  - `random`
  - `ip_hash` (`hash_on`, `hash_key` 커스터마이징)

### 2) 컨트롤 플레인 (Admin)

- 웹 콘솔: `http://localhost:9000/ui`
- 라우트 JSON 편집 + 폼 기반 Route Builder
- 저장 전 Diff Preview
- 라우트 변경 이력/롤백
- Admin 키 관리(RBAC, 키 회전, 비활성화)

### 3) 보안/운영 기능

- Admin RBAC 역할
  - `read`: 조회/검증/미리보기
  - `write`: 생성/수정/삭제/롤백/리로드/키관리
- 감사 로그 파일: `logs/admin_audit.log`
- 변경 이력 파일: `config/route_history.json`
- 키 저장소 파일: `config/admin_keys.json`
- 메트릭/알람
  - Gateway/Admin 액션 메트릭
  - Prometheus 알람 룰: `deployments/monitoring/prometheus-alerts.yaml`

## 주요 기능

- 멀티 프로토콜 게이트웨이 (HTTP, WebSocket, gRPC)
- 플러그인 아키텍처 (JWT, API Key, mTLS, Rate Limit, Circuit Breaker, Logging)
- 라우트 런타임 리로드
- Admin UI 기반 운영
  - Route Editor
  - Route Form Builder
  - History / Rollback
  - Admin Key Rotation
- CI 품질 게이트
  - `ruff`
  - `mypy`
  - `pytest`

## 프로젝트 구조

```text
apigw/
  admin/                      # Admin API + UI
    static/                   # Admin 콘솔 프론트엔드
  gateway/                    # 데이터 플레인 게이트웨이
  config/
    routes.yaml               # 라우팅 규칙
    gateway.yaml              # 글로벌 플러그인 설정
    admin_keys.json           # Admin 키 저장소(실행 중 생성)
    route_history.json        # 라우트 변경 이력(실행 중 생성)
  deployments/
    docker-compose.yaml       # 로컬 실행 스택
    monitoring/
      prometheus-alerts.yaml  # 알람 룰
  tests/
```

## 설치 방법

### 사전 요구사항

- Python 3.11+
- Docker / Docker Compose
- Git

### 설치

```bash
git clone https://github.com/kchul199/OpenApi_GW.git
cd OpenApi_GW/apigw

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 실행 방법

### 1) Redis 실행

```bash
docker compose -f deployments/docker-compose.yaml up -d redis
```

### 2) Gateway 실행 (HTTP 8080, gRPC 9090)

```bash
python -m gateway.main
```

### 3) Admin 실행 (9000)

```bash
python -m admin.main
```

### 4) 기본 확인

```bash
curl http://localhost:8080/_health
curl -H "X-Admin-Key: changeme-admin-key" http://localhost:9000/api/v1/dashboard
```

### 5) 관리 화면 접속

- URL: `http://localhost:9000/ui`
- 기본 Admin Key: `changeme-admin-key`

## 환경설정

주요 설정은 `gateway/config/settings.py` 기준이며, `.env` 또는 환경변수로 주입할 수 있습니다.

### 자주 쓰는 환경변수

- `ADMIN__API_KEY`
- `ADMIN__READ_API_KEYS` (쉼표 구분)
- `ADMIN__WRITE_API_KEYS` (쉼표 구분)
- `ADMIN__KEY_STORE_FILE`
- `ADMIN__AUDIT_LOG_FILE`
- `ADMIN__ROUTE_HISTORY_FILE`
- `ROUTES_CONFIG`
- `GATEWAY_CONFIG`
- `REDIS__URL`
- `OBSERVABILITY__METRICS_ENABLED`
- `OBSERVABILITY__METRICS_PATH`
- `OBSERVABILITY__TRACING_ENABLED`

## 테스트 / 검증

```bash
ruff check gateway admin tests
mypy gateway admin tests
pytest -q
```

특정 관리화면 흐름만 빠르게 확인하려면:

```bash
pytest -q tests/unit/test_admin_app.py tests/e2e/test_admin_console_flow.py
```

## 트러블 슈팅

### 1) `Redis connection` 오류

증상:

```text
Failed to connect to Redis
Error connecting to localhost:6379
```

해결:

1. `docker compose -f deployments/docker-compose.yaml up -d redis` 실행
2. `docker ps`에서 `oag-redis` 상태 확인
3. `REDIS__URL` 값 확인 (`redis://localhost:6379/0`)

### 2) Admin API `401` / `403`

- `401`: 키가 없거나 잘못됨
- `403`: 키는 유효하지만 `write` 권한이 필요한 작업

확인 포인트:

1. `X-Admin-Key` 헤더 전달 여부
2. 키 역할(`read`/`write`)
3. 키 비활성화 여부 (`/api/v1/admin/keys`)

### 3) 저장 후 `config/routes.yaml` 포맷이 바뀜

- Admin 저장 API는 YAML을 표준 포맷으로 재직렬화합니다.
- 의미 차이가 아닌 포맷 차이일 수 있으므로 Diff를 기준으로 확인하세요.

### 4) 포트 충돌 (`8080`, `9000`, `9090`, `6379`)

```bash
lsof -i :8080 -i :9000 -i :9090 -i :6379
```

충돌 프로세스를 정리하거나 포트를 변경하세요.

### 5) 메트릭이 보이지 않음

1. `OBSERVABILITY__METRICS_ENABLED=true`
2. `OBSERVABILITY__METRICS_PATH` 확인 (기본 `/metrics`)
3. Prometheus 스크랩 타겟 경로 확인

## 문서

- 아키텍처: [docs/architecture.md](docs/architecture.md)
- API 스펙: [docs/api_spec.md](docs/api_spec.md)
- Kubernetes 배포: [deployments/kubernetes/README.md](deployments/kubernetes/README.md)

## 라이선스

MIT
