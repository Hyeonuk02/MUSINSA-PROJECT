# Prince Mart k8s 매니페스트

팀원 `deploy/k8s`의 구조(base / legacy / new overlay, Istio 미러링, new egress 격리)를 그대로 따른다.
클러스터 하나(kind `musinsa-phase1`)에 팀원 공통 구성(Istio, observability, Evidence Store)만 올리고, 팀원 앱 스택(legacy/new)은 올리지 않는다.
Prince Mart 스택은 `pm-legacy`, `pm-new` 네임스페이스에 둔다.

| 경로 | 내용 |
|---|---|
| `00-namespaces.yaml` | `pm-legacy`, `pm-new` (`istio-injection=enabled`) |
| `base/` | 앱 3개(order 8085, coupon 8091, payment 8086), 서비스별 MySQL 3개, Kafka, WireMock(매핑 11개), NetworkPolicy |
| `legacy/` | namespace `pm-legacy` + 서비스별 스택 식별자 patch(`EVIDENCE_STACK=legacy`, `EVIDENCE_VERSION=legacy`) |
| `new/` | namespace `pm-new` + 스택 식별자 patch(`EVIDENCE_VERSION=legacy-eq`) + egress 격리(NetworkPolicy, Sidecar) |
| `istio/virtualservice.yaml` | 게이트웨이 표면 `/orders`, `/coupons`, `/payments` -> pm-legacy route + pm-new mirror 100% |
| `tools/curl-pm.yaml` | 검증용 curl pod(pm-legacy `mesh-check`, pm-new `isolation-injected`, `isolation-uninjected`) |

## 적용 순서

```bash
# 1. 팀원 공통 구성(수정 없이 그대로)
kind create cluster --config deploy/k8s/kind-config.yaml
kubectl apply -f deploy/k8s/00-namespaces.yaml
istioctl install -f deploy/k8s/istio/istio-install.yaml -y
kubectl label namespace observability verify default istio-injection=disabled --overwrite
kubectl apply -f deploy/k8s/istio/telemetry.yaml
kubectl apply -f deploy/k8s/observability/
docker build -t evidence-store:phase3.2 evidence-store && kind load docker-image evidence-store:phase3.2 --name musinsa-phase1
kubectl apply -f deploy/k8s/verify/
kubectl apply -f deploy/k8s/istio/gateway.yaml -f deploy/k8s/istio/virtualservice-shadow.yaml

# 2. Prince Mart 이미지(저장소 루트 컨텍스트)
for s in order coupon payment; do
  docker build -f tracks/prince-mart/app/$s-service/DockerFile -t prince-mart/$s-service:base .
  kind load docker-image prince-mart/$s-service:base --name musinsa-phase1
done

# 3. Prince Mart 스택
kubectl apply -f tracks/prince-mart/k8s/00-namespaces.yaml
kubectl apply -k tracks/prince-mart/k8s/legacy
kubectl apply -k tracks/prince-mart/k8s/new
kubectl apply -f tracks/prince-mart/k8s/istio/virtualservice.yaml -f tracks/prince-mart/k8s/tools/curl-pm.yaml

# 4. 토픽(auto.create 꺼짐. 팀원 방식대로 브로커 준비 뒤 만든다. S0 리셋 뒤에도 같은 명령)
for ns in pm-legacy pm-new; do
  kubectl exec -n $ns deploy/kafka -c kafka -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
    --create --if-not-exists --topic payment-events --partitions 1 --replication-factor 1
done
```

S0 리셋은 팀원과 같다: `order-mysql`, `coupon-mysql`, `payment-mysql`, `kafka`를 rollout restart(emptyDir + Recreate) -> 토픽 생성 ->
order 컨슈머 그룹 `order-service`가 `payment-events`를 할당받았는지 확인 -> WireMock journal 비우기(`DELETE /__admin/requests`).

## `istioctl analyze`의 IST0101 (예상된 것)

`istioctl analyze --all-namespaces`는 Error 등급 IST0101 4건을 낸다.

```
Error [IST0101] (VirtualService istio-system/order-shadow) Referenced host not found: "order.legacy.svc.cluster.local"
Error [IST0101] (VirtualService istio-system/order-shadow) Referenced host not found: "coupon.legacy.svc.cluster.local"
Error [IST0101] (VirtualService istio-system/order-shadow) Referenced mirror host not found: "order.new.svc.cluster.local"
Error [IST0101] (VirtualService istio-system/order-shadow) Referenced mirror host not found: "coupon.new.svc.cluster.local"
```

- 원인: 팀원 VS `order-shadow`는 Evidence Store 경로(`/_evidence/`)와 팀원 앱 경로(`/api/orders`, `/api/coupons`)를 한 리소스에 담고 있다.
  Store 경로가 필요해서 이 VS를 수정 없이 적용하지만, 팀원 앱 스택은 올리지 않으므로 `/api/*`의 대상 host가 없다.
- 영향: 없다. `/api/*` 요청만 503이 되고, Prince Mart는 그 경로를 쓰지 않는다. `/_evidence/`는 정상 동작한다.
  Prince Mart VS(`prince-mart-shadow`)에는 지적이 없다.
- 두 VS는 Gateway `order-gateway`, hosts `"*"`가 같아 Istio가 라우트를 합친다. VS 사이 평가 순서는 보장되지 않지만
  prefix(`/_evidence/`, `/api/...`와 `/orders`, `/coupons`, `/payments`)가 서로 겹치지 않아 결과가 같다.

## 팀원 매니페스트와 다른 점

| 항목 | 팀원 | Prince Mart | 이유 |
|---|---|---|---|
| 네임스페이스 | legacy, new | pm-legacy, pm-new | 팀원 스택과 분리 |
| 앱 포트 | 8080 | 8085, 8091, 8086 | upstream `application.yml` 기본값 |
| heap 설정 | `JAVA_TOOL_OPTIONS`에 `-Xmx384m` | 이미지 `JAVA_OPTS`(upstream `-Xmx384M -Xms256M -XX:+UseSerialGC`) | upstream 런타임 옵션 유지. `JAVA_TOOL_OPTIONS`는 agent와 metaspace 상한만 |
| MySQL | 2개, limits 512Mi | 3개(서비스별), limits 768Mi | 실측 working set이 512Mi를 넘음(order DB 520MiB) |
| `EVIDENCE_HEADERS` | ... Idempotency-Key ... | ... X-User-Id ... | Prince Mart의 요청 식별 헤더 |
| Kafka 접근 | order, coupon | order(소비), payment(발행) | 앱 구성 |
| 앱 ingress 정책 | coupon만 | order, coupon, payment 모두 | 세 서비스 모두 같은 스택 안에서 서로 호출된다 |
| new 격리 적용 | 별도 `kubectl apply` | `new/` overlay에 포함 | 빠뜨리지 않게 |
| 주입 라벨 | `kubectl label` | 네임스페이스 매니페스트에 | 재현성 |
