# API Gateway Performance Testing (k6)

이 디렉토리는 오픈 API 게이트웨이의 성능 및 부하 테스트를 위한 [k6](https://k6.io/) 스크립트를 포함하고 있습니다.

## 사전 요구 사항

k6를 로컬 컴퓨터에 설치해야 합니다:
- **macOS (Homebrew):** `brew install k6`
- **Linux (Debian/Ubuntu):** `sudo apt-get install k6`
- **Windows (Chocolatey):** `choco install k6`

## 테스트 실행 방법

### 1. 베이스라인 REST API 부하 테스트

Gateway가 로컬(기본값: `http://localhost:8080`)에 띄워진 상태에서 아래 명령어를 실행합니다:

```bash
k6 run tests/load/rest_load_test.js
```

### 2. 커스텀 환경 변수 (타겟 호스트 변경)

원격 서버 또는 다른 포트를 테스트하려면 `BASE_URL` 환경 변수를 넘겨줍니다.

```bash
k6 run -e BASE_URL=http://api.staging.example.com tests/load/rest_load_test.js
```

### 3. VUs (Virtual Users) 임의 지정

스크립트 내부의 Stages를 무시하고 일시적으로 큰 부하를 주고 싶을 때 사용합니다:

```bash
k6 run --vus 100 --duration 30s tests/load/rest_load_test.js
```

## 주요 확인 지표 (k6 결과 화면)
- `http_req_duration`: 요청 처리 지연 시간 (Latency). P99, P95 값을 주의 깊게 확인하세요.
- `http_reqs`: 전체 발생한 요청 수와 초당 요청 처리 수 (Throughput/RPS).
- `http_req_failed`: 에러 발생률. 이 값이 0%에 수렴해야 안정적인 상태입니다.
