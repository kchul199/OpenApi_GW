# Open API Gateway 아키텍처 설계서

## 1. 시스템 개요 (System Overview)
본 Open API Gateway (OAG)는 K8s 클라우드 네이티브 환경에서 대규모 마이크로서비스 아키텍처(MSA)의 진입점 역할을 수행하기 위해 구축된 중앙 라우팅 파이프라인입니다. FastAPI(Python ASGI)의 논블로킹 I/O 생태계를 기반으로, 범용적인 HTTP 리버스 프록싱뿐만 아니라 gRPC 바이패싱 및 WebSocket 스트림 멀티플렉싱을 지원합니다.

## 2. 코어 아키텍처 매트릭스 (Core Architecture)

```mermaid
graph TD
    Client[대외/클라이언트 트래픽] -->|HTTP 8080, gRPC 9090| L4_L7_LB[K8s Service / Ingress / mTLS]
    L4_L7_LB --> OAG_Pod_1
    L4_L7_LB --> OAG_Pod_N

    subgraph "Gateway (FastAPI + Gunicorn)"
        OAG_Pod_1 --> Routing[Routing Engine]
        Routing --> PluginChain[Middleware Plugin Pipeline]
        PluginChain --> Proxy[Reverse Proxy & Adapters]
    end

    Proxy -->|REST| MSA_A[Service A]
    Proxy -->|gRPC| MSA_B[Service B]
    Proxy -->|ws://| MSA_C[Service C]

    PluginChain <..> RedisCluster[(Redis Cluster <br> Rate Limit, Circuit Breaker)]
```

### 2.1 라우팅 엔진 (Routing Engine)
- `/config/routes.yaml` (단기) 혹은 Kubernetes ConfigMap 에 기재된 선언적 YAML 스펙에 기반하여 라우트를 결정합니다.
- `Match` 속성(Host, Path prefix, Methods 등)을 런타임에 Trie 기반 또는 Regex 방식으로 검증합니다.

### 2.2 플러그인 체인 (Plugin Chain of Responsibility)
- 각 Request는 Gateway Context 객체를 할당받고, 등록된 플러그인 레이어를 순차적으로 통과해야만 실제 백엔드(Upstream)로 포워딩될 자격을 얻습니다.
- **[Layer 1] Auth (인증):** mTLS, API Key, JWT (JWKS 동적 갱신 지원) 등
- **[Layer 2] Rate Limiter:** Redis `EVAL` 루아 스크립트 기반 Sliding Window/Token Bucket으로 트래픽 한도 방어
- **[Layer 3] Circuit Breaker:** 실패 응답 모니터링 및 상태 임계치 초과 시 분산(Circuit Open) Fail-Fast 처리.

### 2.3 스레딩 및 컨커런시 (Concurrency)
- C-based Event Loop (`uvloop`) 및 `httpx.AsyncClient` 커넥션 풀을 베이스로 I/O Wait을 최소화했습니다.
- CPU 바운드 오버헤드(Python GIL) 극복을 위해 K8s 파드 내부 단일 워커를 넘어 노드 성능 기반 HPA 스케일아웃으로 선형 가용성을 보장합니다.

## 3. 고가용성 및 무중단 배포 (High Availability & Zero-Downtime)

### 3.1 동적 설정 핫루프 (Dynamic Hot-Reload)
단일 파드의 설정 적용 한계를 극복하기 위해 `Admin API`에서 리로드 시그널을 수신하면, 내부적으로 Redis Pub/Sub(`oag:config_reload` 채널)을 통해 연결된 모든 Worker Pod 들이 동시에 새로운 `routes.yaml`을 리로딩합니다. 서버 재구동 없는 무중단 반영을 실현합니다.

### 3.2 Kubernetes 매니페스트 (K8s Lifecycle)
- **Liveness Probe:** `/health` API에서 Redis Ping 검사 체인을 수립하여, 분산락 저장소 다운 시 즉각 트래픽 제외 조치 실행합니다.
- **Graceful Shutdown:** `preStop Hook (sleep 10)`으로 SIGTERM 발생 시 기존 처리 커넥션을 안전하게 우회 및 드레인시킵니다.
- **PodDisruptionBudget (PDB) & HPA:** 유지보수 및 자원 한계 시 백업 노드가 항상 1 이상 보장되도록 세팅되었습니다.
