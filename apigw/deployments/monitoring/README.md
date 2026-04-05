# OAG Monitoring Assets

이 디렉토리는 Prometheus/Grafana 연동 시 바로 가져다 쓸 수 있는
경보 규칙과 대시보드 템플릿을 제공합니다.

## 포함 파일

- `prometheus-rules.yaml`: Gateway/Admin 핵심 운영 경보 규칙
- `grafana-dashboard-admin.json`: Admin control-plane 운영 대시보드 템플릿

## 적용 예시

Prometheus Operator를 사용 중이면 아래처럼 적용할 수 있습니다.

```bash
kubectl apply -f deployments/monitoring/prometheus-rules.yaml
```

Grafana에서는 `grafana-dashboard-admin.json`을 Import 하세요.

## 주요 알람

- `OAGGateway5xxHigh`: 5분 평균 5xx 비율 5% 초과
- `OAGAdminAuthFailuresHigh`: 5분간 인증 실패 20건 초과
- `OAGAdminWriteRateLimited`: 관리 write rate limit 이벤트 발생
