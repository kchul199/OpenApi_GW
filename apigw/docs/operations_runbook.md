# OAG Operations Runbook

## 1. 운영 기준

- Admin API는 내부망/허용 IP에서만 접근
- 모든 변경은 `preview -> validate -> save` 순서 준수
- 장애 시 라우트 롤백을 우선 수행하고 원인 분석은 후속 진행

## 2. 일상 점검

1. `GET /_health`, `GET /_ready` 상태 확인
2. `admin_auth_failures_total` 급증 여부 확인
3. `admin_actions_total{status="rate_limited"}` 발생 여부 확인
4. 최근 라우트 변경 이력(`GET /api/v1/routes/history`) 점검

## 3. 사고 대응

### 3.1 Admin 키 유출 의심

1. 유출 키 ID 확인 (`GET /api/v1/admin/keys`)
2. 즉시 비활성화 (`POST /api/v1/admin/keys/{key_id}/deactivate`)
3. 새 키 발급 (`POST /api/v1/admin/keys/rotate`)
4. Secret(`admin-control-plane-secrets`) 교체 및 배포 반영
5. 감사 로그(`admin_audit.log`)에서 유출 시점 전후 변경 추적

### 3.2 잘못된 라우트 배포

1. 증상 확인(5xx 증가, 특정 API 실패)
2. 최근 변경 이력 조회 후 대상 entry 확인
3. 즉시 롤백 (`POST /api/v1/routes/history/{entry_id}/rollback`)
4. `POST /api/v1/reload` 실행 후 정상화 확인

### 3.3 Redis 장애

1. Redis pod 상태/로그 확인
2. Gateway의 `/_health`에서 redis 상태 확인
3. Redis 복구 후 gateway/admin pod 재시작 여부 판단
4. circuit-breaker/rate-limiter 동작 정상 여부 재확인

### 3.4 Admin 인증 실패 급증

1. `admin_auth_failures_total`의 `reason` 라벨 분해 확인
2. `invalid` 급증: 키 오입력/자동화 스크립트 오류 점검
3. `ip_blocked` 급증: allowlist 정책/프록시 IP 전달 체인 점검
4. 공격 의심 시 WAF/Ingress 차단 룰 임시 강화

## 4. 롤백 기준

- 5xx 비율 5% 초과가 10분 지속
- 핵심 API(로그인/결제/주문) 오류율 급증
- Admin write 작업이 반복 실패하고 영향 범위가 확대될 때

위 조건 중 하나라도 만족하면 기능 수정보다 라우트 롤백을 우선합니다.

## 5. 사후 조치

1. 장애 타임라인 정리 (탐지, 대응, 복구 시각)
2. 재발 방지 액션 등록 (알람 임계치, 테스트 보강, 접근 정책 강화)
3. 문서/런북 업데이트 및 온콜 공유
