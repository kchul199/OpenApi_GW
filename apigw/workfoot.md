# Workfoot (변경 이력 로그 및 아키텍처 리뷰)

이 문서는 Open API Gateway(OAG) 설계 및 소스 코드의 수정 내용을 일자별로 기록하는 파일입니다. 

---

## 2026-03-22
**[Phase 1 & 1.5 완료: Core Foundation 및 로컬 K8s 설정]**
- **아키텍처 스택 결정:** Go에서 비동기 처리(asyncio)가 가능한 Python(FastAPI, httpx, grpcio) 스택으로 변경 승인 및 반영.
- **설정 시스템:** Pydantic 과 YAML 기반 라우터 설정 기능 구현. (`gateway/config`)
- **멀티 프로토콜 라우팅 엔진:** 동적 라우팅 엔진, HTTP 리버스 프록시(`httpx` 기반) 및 WebSocket 프록시 기능 구현. (`gateway/core/router.py`, `gateway/core/proxy.py`, `gateway/listeners/websocket_listener.py`)
- **플러그인 시스템 파이프라인:** 인증(JWT, API Key), Rate Limiter, Circuit Breaker, Logging 미들웨어 구현.
- **로컬 쿠버네티스(K8s) 배포 리소스 정리:** `minikube` / `kind` 테스트용 K8s Manifest 작성.

## 2026-03-22 (Phase 2)
**[Phase 2 완료: Architecture Hardening]**
- **분산 Rate Limiter 전환:** 기존 인메모리 방식의 Token Bucket 알고리즘을 Redis 서버의 Lua Script 원자적 연산 기반으로 교체하여, 다중 게이트웨이 Pod 환경에서도 완벽한 트래픽 제한 동기화를 달성함.
- **전역 Redis Client:** `redis.asyncio` 기반 커넥션 풀을 애플리케이션 라이프사이클에 맞춰 연동 완료. (`gateway/core/redis.py`)
- **실시간 Config File Watcher:** 라우터 설정 동적 갱신을 위해 어드민 API의 명시적 `/_reload` 호출 방식과 더불어, Kubernetes ConfigMap 파일 시스템 변경 사항을 자동으로 감지(`os.stat` 폴링)하여 라우터 엔진을 즉각 핫-리로드하는 데몬 태스크 추가 완료. (`gateway/config/watcher.py`)

## 2026-03-22 (Phase 2.5)
**[Phase 2.5 완료: Performance Tuning]**
- **멀티 프로세스 워커 도입:** 기존 단일 스레드 `uvicorn` 실행 방식에서 `gunicorn` 프로세스 매니저와 `UvicornWorker` 조합으로 변경. Dockerfile의 ENTRYPOINT를 수정하여 CPU 코어 활용률을 극대화함. (`WORKERS` 환경변수 배포 지원)
- **초고속 JSON 직렬화:** Python 기본 `json` 모듈 대신 Rust 로 작성된 초고속 `orjson` 라이브러리를 구조화 로깅(`gateway/observability/logging.py`) 및 전체 Gateway 페이로드 병합용으로 교체.
- **성능/부하 테스트 환경 구축:** [k6](https://k6.io/) 기반의 로드 테스트 스크립트(`tests/load/rest_load_test.js`)를 작성하고, 임계치(Threshold) 및 단계별(Stage) VUs 증가 로직이 포함된 벤치마크 환경을 `tests/load/README.md` 가이드와 함께 구성함.

## 2026-03-22 (Phase 3 진행)
**[Phase 3: Protocol & Pipeline Support - gRPC & WebSocket]**
- **gRPC 리스너 및 리버스 프록시 파이프라인 연동:** 
  - `grpc.GenericRpcHandler` 기반의 미지정 타입(Any) gRPC 콜백 핸들러 `GenericGRPCProxy` 구현 (`gateway/adapters/grpc_proxy.py`).
  - Protobuf 스키마 컴파일 구조 없이도 raw stream-stream 프록싱이 가능하도록 Insecure Channel 기반 범용 라우터 연동 처리.
  - FastAPI `_lifespan` 라이프사이클에 비동기 gRPC 서버 구동 시퀀스를 병합하여 단일 애플리케이션 내에서 HTTP(8080)와 gRPC(9090) 리스너가 동시 동작하도록 구현됨.
- **WebSocket 프록시 고도화:**
  - `gateway/listeners/websocket_listener.py` 고도화 진행.
  - 단순 By-pass를 넘어 **서브프로토콜(Subprotocol) 동적 협상** 기능 추가. 클라이언트 요청 서브프로토콜을 업스트림에 먼저 연결한 뒤, 승인된 프로토콜로 클라이언트 커넥션을 수락하도록 생명주기 제어 구조 변경.
  - 텍스트/바이너리 프레임 타입 유동적 멀티플렉싱 처리 로직 보강 (`client.receive()` 활용).

---

## 📝 아키텍처 검증 및 리뷰 리포트 (2026-03-22)

현재 구현된 Phase 1 아키텍처를 엔터프라이즈 및 운영 관점에서 검증한 결과, 아래와 같은 **개선 필요 사항(Tech Debt)**이 도출되었습니다. 

### 1. 분산 환경(Kubernetes)에서의 상태 공유 ✅ (해결 완료 - Phase 2)
- **현재 구현(Phase 1 당시):** `RateLimiterPlugin`이 인메모리(TokenBucket)로 동작했습니다.
- **문제점:** Kubernetes 환경에서 Pod가 여러 개(Replica)로 스케일 아웃될 경우, 각 Pod마다 독립적인 Rate Limit 카운트를 가지게 되어 정확한 트래픽 제어가 불가능했습니다.
- **해결:** Phase 2에서 Redis Lua 스크립트 기반 Token Bucket으로 마이그레이션 완료. 모든 Pod가 동일한 Redis 카운터를 공유합니다 (`gateway/plugins/ratelimit/ratelimit_plugin.py`).
## 📝 2차 아키텍처 검증 및 리뷰 리포트 (Phase 2.5 & Phase 3)

**1. 성능 튜닝 아키텍처 (Phase 2.5)**
- **구현 내용 검증:** FastAPI 기본 런타임 한계를 극복하기 위해 `Gunicorn` 기반 `UvicornWorker` 멀티 프로세스 관리 구조를 Docker 컨테이너 레벨에 아주 잘 안착시켰습니다.
- **성능 검증 방향:** `k6` 부하 테스트가 도입되어 변경 사항에 대한 Throughput 모니터링 기반이 마련되었으며, 무거운 `json` 모듈 대신 `orjson`으로 바닥 공사를 단행한 것은 높은 I/O 병목 해소에 큰 도움이 되는 아키텍처적 개선입니다.

**2. 프로토콜 파이프라인 (Phase 3)**
- **gRPC 리버스 프록시 연동:**
  - `grpc_proxy.py`에서 `GenericRpcHandler`를 사용하여 gRPC의 엄격한 스키마 의존성(Proto 파일 컴파일) 의존성 문제를 우회하고, 진정한 의미의 **범용 API Gateway**로서 기능하게 한 것은 훌륭한 설계입니다. 
  - 다만 `app.py`에서 Uvicorn 워커의 비동기 루프와 `grpc.aio.Server`를 분리 제어하면서 `_lifespan` 훅 안에 깔끔하게 주입하여 라이프사이클 꼬임 현상을 막았습니다.
- **WebSocket 멀티플렉싱 고도화:**
  - 단순 By-pass 파이프로 남겨두지 않고, Subprotocol 협상을 도입하여 클라이언트-게이트웨이-서버 간의 프로토콜 불일치 방어벽을 세운 점이 매우 돋보입니다. 
  - `client.receive()`를 통한 타입리스 메시지 처리로 크래시 예방까지 처리되어 운영 안정성이 확보되었습니다.
- **REST ↔ gRPC 어댑터 (`rest2grpc.py`):**
  - 클라이언트의 HTTP REST JSON 요청을 받아 Upstream gRPC로 채널링하는 기반 구조를 잡았습니다.
  - **향후 개선점 (Action Item):** 완전한 동적 파싱을 위해서는 향후 `grpc_reflection`을 통한 동적 Descriptor 탐색 루틴을 런타임에 올리거나, Envoy처럼 `.pb` 바이너리 디스크립터 파일을 마운트 받아 처리하는 방식이 필요합니다.

**총평:**
Phase 2.5~3을 거치며 `API Gateway`라는 이름에 걸맞은 엔터프라이즈 멀티-프로토콜(REST, WS, gRPC) 수용 능력을 안정적으로 확보했습니다. 코드 베이스가 깔끔하게 분리되어 있으며(SOLID 원칙), 설계 의도대로 플러그인과 핸들러가 체인으로 결합되고 있습니다. 이제 인가/인증 및 서킷 브레이커, Rate Limiter 같은 실질적인 Edge Layer 필터 룰을 적용해 나갈 완벽한 타이밍입니다.

---

## 2026-03-22 (Phase 4 진행 완료)
**[Phase 4: Security & Reliability]**
- **Distributed Circuit Breaker (서킷 브레이커 이중화/분산화):**
  - 기존 메모리 기반 서킷 브레이커를 **Redis 기반의 분산 서킷 브레이커**로 업그레이드 하였습니다 (`gateway/plugins/circuitbreaker/breaker_plugin.py`).
  - 멀티 노드/워커 환경에서도 특정 라우트(Upstream)의 장애 상태(OPEN)가 즉각적으로 글로벌 전파되도록 구현하여 불필요한 장애 전파 리소스를 완벽히 차단했습니다 (`cb:open:{route_id}` 및 `cb:fails:{route_id}` 활용).
- **JWT 검증 플러그인 고도화 (JWKS 지원):**
  - 단순 정적 Secret Key 검증을 넘어, Auth0, Keycloak 등 외부 IdP 환경 연동에 필수적인 **JWKS(JSON Web Key Set) 동적 암호키 조회 구조**를 추가했습니다 (`gateway/plugins/auth/jwt_plugin.py`).
  - 플러그인 설정에 `jwks_url`이 주입된 경우 외부에서 공개 키 셋을 동적으로 불러와(lru_cache 적용) 검증합니다.
- Rate Limiter 분산 이중화는 Phase 2 단계에서 Lua 스크립트로 선행 완료되었으므로 Phase 4 체크 완료.

## 2026-03-22 (Phase 4.5 진행 완료)
**[Phase 4.5: Observability & Admin]**
- **Prometheus 메트릭 통합:** `prometheus-fastapi-instrumentator`를 통해 Gateway의 API 지연율(Latency), 에러율, Throughput 등을 수집하는 엔드포인트(`/metrics`)를 메인 파이프라인에 활성화 하였습니다.
- **OpenTelemetry 트레이싱 구성:** 분산 트랜잭션 추적을 위해 `opentelemetry-sdk`를 게이트웨이 파이프라인(`gateway/app.py`)에 안착시켰습니다. `OTEL_EXPORTER_OTLP_ENDPOINT` 환경변수 유무에 따라 OTLP 내보내기 또는 Console 로깅으로 동적 전환됩니다.
- **Admin REST API 검증:** `admin/app.py`를 통해 라우팅 정보 리로드(`/_reload`), 설정 조회, 플러그인 레지스트리 조회를 수행하는 컨트롤 플레인이 정상적으로 구성되어 있음을 확인하였습니다.

## 2026-03-22 (Phase 5 진행 완료)
**[Phase 5: Production Hardening]**
- **mTLS Enforcer 플러그인 도입:**
  - 엣지 로드밸런서(Envoy, Nginx, ALB 등) 레벨에서 TLS Termination된 후 전달되는 클라이언트 인증서 헤더(예: `x-client-cert`)를 검사하여 상호 인증을 강제하는 `mtls-enforcer` 플러그인을 파이프라인(`gateway/plugins/auth/mtls_plugin.py`)에 추가했습니다. 허용된 인증 주체(Subject DN) 기반 제어 기능을 포함합니다.
- **Kubernetes 배포 매니페스트 고도화:**
  - 기존 Gateway Deployment 및 Service 코드를 운영 레벨에 맞추어 보강하였습니다.
  - 리소스 부하(CPU, Memory) 기반 오토스케일링을 수행하는 **HPA(HorizontalPodAutoscaler)** 매니페스트(`06-hpa.yaml`)를 작성했습니다.
  - 무중단 롤링 배포 및 노드 장애 시 최소 가용성을 보장하기 위해 **PDB(PodDisruptionBudget)** 매니페스트(`07-pdb.yaml`)를 추가 작성하여, 클러스터 스케일링 간 안정성을 확보했습니다.

---
### 2. Config Hot-Reload의 한계 ✅ (해결 완료 - Phase 2)
- **현재 구현(Phase 1 당시):** Admin API의 `POST /_reload`를 호출하면 요청을 받은 1개의 Pod만 설정이 갱신되었습니다.
- **해결:** Phase 2에서 두 가지 방식으로 이중화 완료.
  1. **Redis Pub/Sub 브로드캐스트:** Admin API가 `oag:config_reload` 채널로 발행 → 모든 Gateway Pod가 동시 리로드.
  2. **ConfigFileWatcher:** `os.stat` 기반 **5초** 간격 폴링으로 ConfigMap 파일 변경 자동 감지 및 핫-리로드 (`gateway/config/watcher.py`).

### 3. gRPC 파이프라인 통합 미흡 (Medium)
- **현재 구현:** `grpc_listener.py`에 gRPC 서버 뼈대만 존재합니다.
- **문제점:** HTTP(FastAPI)와 동일한 미들웨어 파이프라인(Auth, Rate Limit)을 타지 못합니다. 
- **개선 방안:** gRPC 인터셉터(Interceptor)를 구현하여 GatewayContext와 기존 플러그인 파이프라인을 gRPC 요청에도 붙일 수 있도록 어댑터 패턴을 구현해야 합니다.

### 4. Python Worker 프로세스 및 성능 ✅ (해결 완료 - Phase 2.5)
- **현재 구현(Phase 1 당시):** Dockerfile에서 Uvicorn 단일 워커로 실행되었습니다.
- **해결:** Phase 2.5에서 Gunicorn + UvicornWorker 멀티 프로세스 구조로 전환. `WORKERS` 환경변수로 워커 수 조정 가능. K8s HPA와 연계한 Pod 수평 확장도 지원합니다.

### 5. Circuit Breaker 상태 동기화 (Low) -> (해결 완료)
- Phase 4에서 Redis 기반의 분산 서킷 브레이커로 업그레이드하여 멀티-노드 가용성을 확보하였습니다.

---

## 📝 최종 아키텍처 검증 및 리뷰 리포트 (Phase 1 ~ Phase 5 구축 완료)

**1. 로드맵 달성도 (100%)**
- **Phase 1 (Core Foundation):** FastAPI 기반 라우팅 엔진 및 미들웨어 플러그인 체인 확립.
- **Phase 2 ~ 2.5 (Hardening & Performance):** Redis 분산 Rate Limiter, `orjson` 적용, Gunicorn 워커 적용으로 엔터프라이즈 트래픽 수용 능력 달성.
- **Phase 3 (Protocol Pipeline):** HTTP/REST, gRPC, WebSocket의 3대 프로토콜을 단일 런타임에서 멀티플렉싱하는 범용 게이트웨이 파이프라인 완성. 
- **Phase 4 & 4.5 (Security & Observability):** JWKS 동적 인증, 분산 서킷 브레이커, OpenTelemetry 추적, Prometheus 메트릭 수집 및 Admin API를 아우르는 운영 안전망 구축.
- **Phase 5 (Production Hardening):** mTLS Enforcer (Client Cert 헤더 기반 검증) 및 K8s HPA, PDB 매니페스트 구축 완료.

**2. 아키텍처 강점 (Strengths)**
- **플러그인 체인 체계 (Chain of Responsibility):** Auth, Rate Limit, Circuit Breaker 등이 완벽히 디커플링(Decoupling)되어 코어 비즈니스 로직(라우팅 등)을 건드리지 않고 확장이 가능합니다.
- **Python ASGI 성능 한계 극복:** Uvicorn 단일 워커의 한계를 Gunicorn Process Manager로 풀어내었고, `orjson`과 Redis 비동기 클라이언트를 적극 차용하여 I/O 바운드 병목을 최소화했습니다.
- **Kubernetes-Native 지향:** K8s HPA/PDB 등 운영 매니페스트 제공과 Redis 분산 락/저장소를 활용한 상태 공유로 Stateful하지 않은 무상태(Stateless) 아키텍처를 잘 유지했습니다.

**3. 향후 발전 과제 (Tech Debt & Next Steps for v2.0)**
- **gRPC 동적 디스크립터 매핑:** 현재 구현된 `GenericGRPCProxy`는 바이패스 수준이므로, 향후 Header 조작이나 로드밸런싱 라우트를 위해 `grpc_reflection`을 붙인 동적 gRPC 메타정보 로더 빌드가 필요합니다.
- **K8s Custom Resource Definition (CRD):** 현재 `routes.yaml`을 ConfigMap으로 관리 중이나, K8s Native 확장을 위해 `GatewayRoute`, `GatewayPlugin` 등 커스텀 리소스 기반의 Kubernetes Ingress Controller(Operator) 형태로 진화시키는 것이 이상적입니다.
- **CI/CD 및 e2e 테스트 강화:** GitHub Actions를 도입해 로컬 테스트(pytest)와 k6 부하 검증을 배포 시마다 자동화하는 파이프라인 구축이 요구됩니다.

**총평:**
초기 목표였던 **엔터프라이즈 멀티-프로토콜 오픈 API 게이트웨이** 설계가 성공적으로 파이프라인의 끝을 맺었습니다. 단일 Monolithic 서버 형태에서 시작해, 완전한 분산형 마이크로서비스 관문의 역할을 수행할 수 있는 완성도 높은 아키텍처 구조를 띠고 있습니다.

---

## 🛠️ 쿠버네티스 운영자 관점의 심층 아키텍처 점검 및 개선 제안 

Kubernetes 환경에서의 대규모 트래픽 운영(Day-2 Operations) 관점에서 전체 소스 코드를 면밀히 점검한 결과, 아래와 같은 4가지 핵심 개선(Enhancement) 사항을 제안합니다.

### 1. [안정성] Health Probe (Liveness/Readiness) 로직 고도화 (Critical)
- **현행:** `gateway/app.py`의 `/_health` 엔드포인트에서 `await get_redis().ping()`으로 Redis 연결 상태를 실시간 점검하고, 실패 시 503을 반환합니다. ✅ **구현 완료**
- **잔여 과제:** `/_ready` 엔드포인트는 현재 단순히 `{"status": "ready"}`만 반환합니다. 라우트 로딩 완료 여부 등 실질적인 레디니스 조건을 추가하는 것을 권장합니다.

### 2. [안정성] Graceful Shutdown 및 preStop 훅(Hook) 설계 보강 (High)
- **현행:** FastAPI `_lifespan` 훅에서 Proxy 클라이언트와 Redis 커넥션을 셧다운(`aclose()`)하고 있으나, K8s 매니페스트(`04-gateway.yaml`)에는 `preStop` 훅이 부재합니다.
- **점검 소견:** Kubernetes에서 파드를 롤링 업데이트할 때 503 에러 리포트(Downtime)가 발생할 수 있습니다. Kubelet이 파드를 제거(Terminating)하더라도 Kube-proxy의 iptables 룰이 갱신되기 전까지 미세한 시간 동안 기존 파드로 트래픽이 인입될 수 있기 때문입니다.
- **개선 제안:** Deployment 매니페스트에 K8s `preStop: exec: command: ["/bin/sleep", "10"]` 훅을 삽입하여, SIGTERM 시그널 수신 전에 유예 기간을 두어 K8s 트래픽 라우팅망이 먼저 정리되도록 유도(Traffic Draining)해야 합니다.

### 3. [유연성] 라우팅 룰 설정 관리 패턴 최적화: Polling vs K8s API (Medium)
- **현행:** `gateway/config/watcher.py`가 **5초** 간격으로 `os.stat` 폴링을 통해 ConfigMap 볼륨의 파일 변경을 감지하고 핫-리로드합니다.
- **점검 소견:** Kubernetes ConfigMap이 Pod의 마운트 볼륨에 반영되는 데 Kubelet 동기화 주기로 인해 최대 1분 내외의 지연이 발생할 수 있습니다. 폴링 방식은 클러스터 노드 리소스를 점유하며 즉각적인 반영을 보장하지 않습니다.
- **개선 제안 (장기 과제):** 인프라 레벨의 K8s RBAC 권한을 부여하고, K8s SDK(Client-Python)의 `Watch` 리스너를 활용하는 **Kubernetes Operator / Informer 패턴**을 도입하는 것이 가장 Cloud-Native한 접근입니다. 궁극적으로는 Gateway API CRD 모델(`GatewayRoute`)로 진화하는 것을 권장합니다.

### 4. [확장성] Redis Cluster/Sentinel 연결 지원 확대 (Medium)
- **현행:** `gateway/core/redis.py`에서 `settings.redis.cluster_mode` 플래그에 따라 단일 인스턴스(`Redis`) 또는 클러스터(`RedisCluster`) 모드로 분기하여 연결합니다. ✅ **구현 완료**
- **잔여 과제:** Redis Sentinel 모드 지원 및 클러스터 토폴로지 자동 갱신(Cluster Refresh) 설정 추가를 장기 과제로 남겨둡니다.
