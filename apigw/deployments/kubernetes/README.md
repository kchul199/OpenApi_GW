# Local Kubernetes Environment for OAG

Kubernetes native 환경 운영을 위한 로컬 테스트/검증 환경입니다.  
`minikube` 또는 `kind`를 사용하여 로컬에서 게이트웨이를 테스트할 수 있습니다.

## 1. 클러스터 시작

**Minikube를 사용하는 경우:**
```bash
minikube start
```

**Kind를 사용하는 경우:**
```bash
kind create cluster --name oag-cluster
```

## 2. Docker 이미지 빌드 및 로드

K8s 클러스터 내부에서 로컬 이미지를 사용할 수 있도록 이미지를 빌드하고 로드합니다.

```bash
# Gateway & Admin 이미지 빌드 (apigw 루트 디렉토리에서 실행)
docker build -t open-api-gateway:local . -f deployments/Dockerfile

# Minikube에 이미지 로드
minikube image load open-api-gateway:local

# 또는 Kind에 이미지 로드
kind load docker-image open-api-gateway:local --name oag-cluster
```

## 3. 리소스 배포

`kubectl apply` 명령어를 사용하여 전체 리소스를 배포합니다.

먼저 Admin API 키를 Secret에 주입합니다.

```bash
# 기본 템플릿 파일 수정
vi deployments/kubernetes/base/08-admin-secrets.yaml

# 혹은 즉시 덮어쓰기
kubectl create secret generic admin-control-plane-secrets \
  -n oag-system \
  --from-literal=admin_api_key='replace-with-strong-key' \
  --from-literal=read_api_keys='' \
  --from-literal=write_api_keys='' \
  --dry-run=client -o yaml | kubectl apply -f -
```

필요하면 Admin 정책 ConfigMap을 커스터마이징합니다.

```bash
vi deployments/kubernetes/base/10-admin-policy-config.yaml
```

Admin runtime state(`admin_keys.json`, `route_history.json`, `admin_audit.log`)는
`admin-runtime-pvc`에 영속 저장됩니다.

```bash
kubectl apply -f deployments/kubernetes/base/
```

배포 상태 확인:
```bash
kubectl get all -n oag-system
```

## 4. 접속 테스트

**Minikube 터널링 (LoadBalancer 접속):**
```bash
minikube tunnel
```

다른 터미널에서 API Gateway 호출:
```bash
# Public Health Route 테스트
curl -i http://localhost/health

# Mock API Route 테스트
curl -i http://localhost/api/mock/test
```

Admin API 접속:
```bash
# 로컬 포트 포워딩
kubectl port-forward svc/admin -n oag-system 9000:9000

# Admin API 라우트 확인
curl -H "X-Admin-Key: replace-with-strong-key" http://localhost:9000/api/v1/routes
```

## 5. 라우트 시크릿 주입(선택)

`config/routes.yaml`은 `${ENV}` / `${ENV:-default}` 형식의 환경변수 치환을 지원합니다.
예: `${OAG_USER_JWT_SECRET:-dev-secret}`

Pod 환경변수로 주입하면 플러그인 시크릿을 파일에 하드코딩하지 않아도 됩니다.

## 6. 클린업

```bash
kubectl delete -f deployments/kubernetes/base/
```
