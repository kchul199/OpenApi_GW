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

`kubectl apply` 커명령어를 사용하여 전체 리소스를 배포합니다.

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
curl -H "X-Admin-Key: changeme-admin-key" http://localhost:9000/api/v1/routes
```

## 5. 클린업

```bash
kubectl delete -f deployments/kubernetes/base/
```
