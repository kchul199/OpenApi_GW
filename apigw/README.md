# Open API Gateway (OAG)

엔터프라이즈 환경을 위한 고성능, 다중 프로토콜(REST, gRPC, WebSocket) 지원 마이크로서비스 API 게이트웨이입니다. Python ASGI 프레임워크인 FastAPI를 기반으로 구축되었으며, 쿠버네티스 네이티브(Kubernetes-Native) 운영 환경에 최적화되어 있습니다.

## 🌟 주요 특장점 (Features)
- **Multi-Protocol 지원:** HTTP/REST, gRPC, WebSocket 트래픽을 단일 포트에서 핸들링.
- **플러그인 아키텍처 (Plugin-based):** 인증(JWT, API Key, mTLS), 속도 제한(Rate Limit), 서킷 브레이커(Circuit Breaker), 로깅 등의 기능을 손쉽게 탈부착.
- **분산 고가용성 (High Availability):** Redis Cluster 처리를 통한 인가 대기열 방어 및 클러스터 단위 서킷 브레이커.
- **핫-리로드 동기화 (Hot-Reload):** 무중단(Zero-Downtime) 라우팅 룰 변경 (K8s ConfigMap + Redis Pub/Sub).
- **관측성 (Observability):** OpenTelemetry 트레이싱 및 Prometheus 메트릭 수집 기본 제공.

---

## 🚀 시작하기 (초보자 가이드)

### 1️⃣ 사전 요구사항 (Prerequisites)
이 프로젝트를 실행하기 위해 시스템에 다음 프로그램이 설치되어 있어야 합니다.
- **Python 3.11+**
- **Docker & Docker Compose** (로컬 Redis 및 컨테이너 테스트 용도)
- **Git**

### 2️⃣ 환경 구성 및 설치 (Installation)
**1. 소스 코드 가져오기**
```bash
git clone https://github.com/kchul199/OpenApi_GW.git
cd OpenApi_GW
```

**2. 가상환경 생성 및 의존성 설치**
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux 의 경우
# Windows의 경우: venv\Scripts\activate

pip install -r requirements.txt
```

**3. 로컬 Redis 실행**
게이트웨이의 핵심 기능(Rate Limiting 등)은 Redis를 필수로 요구합니다. Docker를 활용해 실행합니다.
```bash
docker-compose up -d redis
```

### 3️⃣ 게이트웨이 실행하기 (Running the Gateway)
아래 명령어를 통해 메인 게이트웨이 서버와 어드민 관리자 통합 API 서버를 실행합니다.
```bash
# gateway 디렉토리로 이동하여 서버 구동 (기본 포트 8080)
python -m gateway.main
```
실행이 완료되면 아래와 같은 로그가 출력됩니다.
* `HTTP started on 8080`
* `gRPC Proxy started on 9090`
* `Admin API started on 9000`

---

## 🧪 테스트 및 검증 (Testing)

### 1) 게이트웨이 기본 헬스체크 (Liveness)
게이트웨이 서버와 Redis 연결 상태를 점검합니다.
```bash
curl http://localhost:8080/_health
# 정상 응답: {"status": "ok", "routes": <라우트개수>, "redis": "ok"}
```

### 2) 테스트 모의 서버(Mock Server) 띄우기
게이트웨이가 트래픽을 포워딩할 가짜 서버(HTTP)를 띄워봅시다. 폴더를 열고 분리된 터미널 탭에서 다음을 실행합니다.
```bash
python -m http.server 8081
```

### 3) 통신 라우팅 테스트
기본적으로 `config/routes.yaml` 설정 파일에 라우팅 규칙이 정의됩니다. `/mock/` 경로를 `http://localhost:8081`로 보내도록 라우팅이 되어있다고 가정하면, 게이트웨이(8080)를 통해 8081로 접근할 수 있습니다.
```bash
curl http://localhost:8080/mock/
# 응답 파일 목록 출력
```

### 4) 어드민 API 조작 (라우트 리로드)
Config 파일(`config/routes.yaml`)을 편집하여 새로운 룰을 저장한 후, 서버 재시작 없이 무중단으로 설정을 갱신하려면 어드민 포트를 호출합니다.
```bash
# _key는 settings.py 또는 환경변수로 설정된 Admin API Key입니다. (기본값: changeme-admin-key)
curl -X POST "http://localhost:9000/api/v1/reload?_key=changeme-admin-key"
```

### 5) 성능 및 부하 테스트 (K6)
대규모 트래픽 부하 검증을 원하신다면 K6 툴킷을 활용하세요.
```bash
k6 run tests/load/rest_load_test.js
```

---

## 📚 추가 문서 자료
시스템 내부 설계와 플러그인 상세 개발 스펙을 알고 싶으시다면 `docs/` 폴더 내의 산출물을 참조해 주세요!
- 🏛️ [아키텍처 설계서 (Architecture)](docs/architecture.md)
- 🔌 [API 연동 및 플러그인 규격서 (API Specs)](docs/api_spec.md)
- 🐳 [쿠버네티스 운영 가이드 (K8s Deploy)](deployments/kubernetes/README.md)
