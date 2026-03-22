# Open API Gateway 연동 및 규격서

## 1. 시스템 인터페이스 개요
Open API Gateway는 백엔드 인프라를 외부로 노출하는 진입점 역할을 수행하며 어드민 관리를 위한 독자적인 API 포트(`9000`)와 서비스 트래픽 포트(`8080`, `9090`)를 수직 분리하여 운영합니다.

## 2. 라우팅 룰(Route Rule) 정의 규격
모든 엔드포인트는 K8s ConfigMap 이나 `config/routes.yaml`을 통해 제어됩니다.

```yaml
# 예시: routes.yaml
- id: "payment-service-v1"
  match:
    path: "/payments/**"
    methods: ["POST", "GET"]
  upstream:
    type: "http"
    url: "http://payment-svc.default.svc.cluster.local:8080"
    timeout: 3.0
    retry:
      count: 3
      backoff_factor: 0.5
      status_codes: [502, 503, 504]
  preserve_host: true
  strip_prefix: true
  plugins:
    - name: rate_limit
      config:
        rate: 100        # 초당 100건 제한
        burst: 200
        by_ip: true
    - name: jwt_auth
      config:
        jwks_url: "https://auth.example.com/.well-known/jwks.json"
```

### 필수 항목 사양:
- `id`: 라우트 고유 식별자. 로깅과 트레이싱 TraceSpan의 핵심 키로 사용됩니다.
- `match`: 클라이언트가 호출하는 패스와 HTTP Method(GET, POST 등) 조합 패턴. (`**`는 하위 경로 와일드카드)
- `upstream`: 실제 데이터 처리가 일어나는 백엔드 URL과 재시도(Retry) 허용 횟수를 명시합니다.
- `plugins`: 특정 Route에만 선택적으로 끼워넣을 게이트웨이 미들웨어 리스트입니다.

## 3. 내장 플러그인 (Plugins) 규격

1. **`api_key_auth` 플러그인**
   - **기능:** `x-api-key` 헤더를 검사하여 `config.keys` 배열에 등록된 토큰인지 판별.
   - **응답:** 매칭 안될 시 HTTP `401 Unauthorized` 예외 반환.

2. **`jwt_auth` 플러그인**
   - **기능:** `Authorization: Bearer <token>` 헤더 압축 해제 및 서명 검증.
   - **기능:** 외부 인증 기관 연동으로 실시간 퍼블릭 키(JWKS) 다운로드 캐싱 적용. 

3. **`mtls_enforcer` 플러그인**
   - **기능:** L4(Envoy 등)단에서 인증된 `X-Client-Cert` 정보를 읽어들여 클라이언트 인증서의 `Subject DN` 검사 수행.

4. **`circuit_breaker` (Redis 분산)**
   - **기능:** 에러 비율이 임계치(`error_threshold`, 기본 50%)를 초과하면 상태를 Open으로 변경. 
   - **기능:** 이후 요청은 즉각 `503 Service Unavailable` 를 발생시켜 장애 노드의 연쇄 장애 폭풍(Cascading Failure)을 방지함.

## 4. 어드민 관리 (Admin API) 규격

관리자 조작을 위한 내부 포트 9000 서버 스펙입니다. Authorization을 위해 요청 헤더 또는 쿼리 스트링으로 `_key` 를 삽입해야 합니다.

### 4.1. 라우트 핫-리로드 동기화
* **URI:** `POST /api/v1/reload`
* **Query:** `?_key=changeme-admin-key`
* **설명:** 백엔드 ConfigMap 파일에서 읽어들여 라우트 상태(Routing Engine)를 갱신합니다. 게이트웨이 팟 전체에 Pub/Sub 으로 브로드캐스팅됩니다.
* **응답 예시:**
    ```json
    {
      "status": "reloaded",
      "routes": 25
    }
    ```

### 4.2. 시스템 헬스체크 (Public)
어드민 토큰 없이 인프라 K8s 시스템에서 체크 가능한 엔드포인트
* **URI:** `GET http://localhost:8080/_health`
* **설명:** Redis 스레드 풀, Uvicorn Worker, Route Engine 생존 유무 점검.
* **응답 예시 (정상):**
    ```json
    {
      "status": "ok",
      "routes": 25,
      "redis": "ok"
    }
    ```
