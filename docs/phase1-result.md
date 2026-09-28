# Phase 1 실행 결과

`docs/phase1-plan.md`의 각 단계에 대한 확정 버전과 확인 결과를 기록한다.

## 고정 버전

| 항목 | 값 | 근거 |
|---|---|---|
| kind | `v0.33.0` (go1.27.1 darwin/arm64) | 계획의 `>= v0.25.0` 조건 충족. 기본 kindnetd가 NetworkPolicy를 지원 |
| kindest/node | `kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0` | Istio 1.31 공식 지원 범위(k8s 1.32~1.36) 안. 로컬 `kubectl v1.34.1`과 1 minor 차이로 스큐 정책 허용 범위 |
| Istio | `1.31.1` | 최신 안정 릴리스 계열. [Announcing Istio 1.31](https://istio.io/latest/news/releases/1.31.x/announcing-1.31/) — "officially supported on Kubernetes versions 1.32 to 1.36" |
| 클러스터 이름 | `musinsa-phase1` (kubectl context `kind-musinsa-phase1`) | |
| Ingress 진입점 | host `80` → node `30080`, host `443` → node `30443` (extraPortMappings) | kind에는 LoadBalancer 구현이 없다. Phase 2의 k6가 클러스터 밖에서 Ingress로 반복 요청하므로 port-forward 프로세스에 의존하지 않는 호스트 포트를 쓴다 |

kind v0.33.0이 제공하는 노드 이미지 중 `v1.37.0`은 Istio 1.31 지원 범위 밖이라 제외했다.

정의 파일: `deploy/k8s/kind-config.yaml`, `deploy/k8s/00-namespaces.yaml`

---

## 1.1 클러스터와 네임스페이스 — 완료

### 노드

```
$ kubectl get nodes -o wide
NAME                           STATUS   ROLES           VERSION   OS-IMAGE                       CONTAINER-RUNTIME
musinsa-phase1-control-plane   Ready    control-plane   v1.35.8   Debian GNU/Linux 13 (trixie)   containerd://2.3.4
```

`kubectl version` → Client `v1.34.1` / Server `v1.35.8` (skew 1, 허용 범위).

### Ingress 진입점 (호스트 포트)

kind의 ingress 표준 패턴을 따랐다. 노드에 `ingress-ready=true` 라벨을 붙이고
(1.2에서 Istio Ingress Gateway를 이 노드에 고정), 노드의 NodePort 대역을 호스트 포트에 매핑했다.

```
$ kubectl get node musinsa-phase1-control-plane -o jsonpath='{.metadata.labels.ingress-ready}'
true

$ docker port musinsa-phase1-control-plane
6443/tcp -> 127.0.0.1:58092
30080/tcp -> 0.0.0.0:80
30443/tcp -> 0.0.0.0:443
```

경로가 실제로 뚫려 있는지 임시 NodePort(30080) Service로 확인했다 — Mac에서 직접:

```
$ curl -s -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" http://localhost/
http_code=200 time=0.003338s
```

1.2에서 `istio-ingressgateway` Service를 `type: NodePort`(http2 → 30080, https → 30443)로
설정하면 `http://localhost/`가 그대로 게이트웨이 진입점이 된다.

### 네임스페이스

`legacy`, `new`, `verify`, `observability` 4개 Active.
`istio-system`은 1.2의 `istioctl install`이 생성한다.

### Order 이미지 적재

Phase 0 앱(`poc/nginx-mirroring/app`, 멀티스테이지 Dockerfile)을 `order-app:phase0`으로 빌드해
`kind load docker-image`로 노드에 넣었다.

```
$ docker exec musinsa-phase1-control-plane crictl images | grep order
docker.io/library/order-app   phase0   7d3e37a47732e   154MB
```

Pod 기동은 1.3a에서 확인한다 (DB 없이는 뜨지 않음).

### NetworkPolicy 스모크 — 통과

임시 네임스페이스 `np-smoke`에 nginx 서버 pod + Service, `curlimages/curl` client pod를 띄우고
`http://web.np-smoke.svc.cluster.local/`로 3단계 확인. 각 curl은 `--max-time 5`.

| 단계 | 조건 | 결과 |
|---|---|---|
| 1 | 정책 없음 | `http_code=200 time=0.001721s` |
| 2 | web pod 선택 default-deny ingress 적용 | `http_code=000 time=5.004322s`, curl exit 28 (타임아웃) |
| 3 | 정책 삭제 | `http_code=200 time=0.001308s` |

적용한 정책:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-ingress-web
  namespace: np-smoke
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Ingress
```

기본 kindnetd에서 NetworkPolicy가 실제로 적용되므로 **별도 CNI 검토는 필요 없다.**
1.5의 격리 증명(egress default-deny)이 이 CNI 위에서 성립한다는 전제가 확인되었다.
확인 후 `np-smoke` 네임스페이스는 삭제했다.

---

## 1.2 Istio 설치와 sidecar 주입 — 완료

정의 파일: `deploy/k8s/istio/istio-install.yaml`, 설치 기록: `deploy/k8s/istio/README.md`

### 설치

```bash
brew install istioctl                                          # 1.31.1
istioctl install -f deploy/k8s/istio/istio-install.yaml -y      # profile=default
```

```
$ istioctl version
client version: 1.31.1
control plane version: 1.31.1
data plane version: 1.31.1 (1 proxies)
```

프로파일은 `default`(istiod + istio-ingressgateway)이고, 거기에 두 가지만 덧붙였다.
`istio-ingressgateway` Service를 `type: NodePort`(80→30080, 443→30443)로 고정하고
`nodeSelector: ingress-ready=true`를 줬다. kind에는 LoadBalancer 구현이 없어
기본값이면 Service가 Pending으로 남고, 1.1에서 뚫은 호스트 포트와 이어지지 않는다.

```
$ kubectl get svc -n istio-system istio-ingressgateway
NAME                   TYPE       CLUSTER-IP     PORT(S)
istio-ingressgateway   NodePort   10.96.216.76   15021:30513/TCP,80:30080/TCP,443:30443/TCP
```

`Gateway` / `VirtualService`는 1.6에서 만든다.

### sidecar 주입

`legacy`, `new`에 `istio-injection=enabled`.
`observability`, `verify`, `default`는 메시에 넣을 이유가 없어 `istio-injection=disabled`로 명시했다
(라벨이 없으면 `istioctl analyze`가 IST0102 Info를 낸다).

`legacy`에 샘플 curl pod `inject-check`를 띄워 확인했다. 이 pod는 1.3b의 메시 경유 확인에 다시 쓴다.

```
$ kubectl get pod inject-check -n legacy
NAME           READY   STATUS    RESTARTS   AGE
inject-check   2/2     Running   0          5s
```

**`istio-proxy`는 `.spec.containers`가 아니라 `.spec.initContainers`에 있다.**
Istio 1.31은 Kubernetes native sidecar(`restartPolicy: Always` initContainer)를 기본으로 쓴다.
계획서의 "컨테이너 2개(app, istio-proxy)" 기준은 `READY 2/2`로 충족된다.

```
$ kubectl get pod inject-check -n legacy -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}{end}'
istio-init
istio-proxy
```

### 검증

```
$ istioctl analyze --all-namespaces
✔ No validation issues found when analyzing all namespaces.
```

## 1.3a 앱 배포 (기능) — 완료

정의 파일: `services/order/`, `deploy/k8s/base/`, `deploy/k8s/legacy/`, `deploy/k8s/new/`

### 앱 전환 (Phase 0 → services/order)

`poc/nginx-mirroring/app`을 `services/order`로 복사한 뒤 아래만 바꿨다. Phase 0 코드는 그대로 둔다.

| 대상 | 변경 |
|---|---|
| `pom.xml` | `org.postgresql:postgresql` → `com.mysql:mysql-connector-j` |
| `application.yml` | `jdbc:mysql://mysql:3306/orders?serverTimezone=UTC`, `hibernate.dialect: org.hibernate.dialect.MySQLDialect`, `spring.sql.init.mode: never` |
| `schema.sql` | 앱에서 제거하고 `deploy/k8s/base/mysql-initdb/schema.sql`로 이동 (MySQL 문법) |
| `ClockConfig.java` (신규) | `APP_FIXED_CLOCK` → `Clock.fixed(..., UTC)`, 비어 있으면 `Clock.systemUTC()` |
| `Order.java` / `OrderController.java` | `Instant.now()` → 주입된 `Clock` 사용 |
| `Dockerfile` | `ENTRYPOINT`에 `-Duser.timezone=UTC` |

`RequestLogFilter`는 건드리지 않았다. `arrivedAt`/`completedAt`은 실측 타이밍이라 고정 시각과 무관하다.

**스키마 소유자는 MySQL init SQL 하나다.** 앱은 DDL을 만들지 않는다(`sql.init.mode: never`).
DDL 사본이 둘이면 "emptyDir + init SQL 재실행 = S0 리셋"이라는 성질이 흐려지고 Phase 2에서 어긋난다.

`TIMESTAMPTZ` → `DATETIME(6)`. MySQL에는 timezone-aware 타입이 없어, 세션 타임존
(`serverTimezone=UTC`)과 JVM 타임존을 UTC로 고정하고 UTC 값을 그대로 저장한다.
`TIMESTAMP`는 2038년 상한이 있어 쓰지 않았다.

### 배포

`deploy/k8s/base/`(네임스페이스 없음) + `legacy`/`new` overlay. 두 overlay의 차이는 `namespace`뿐이다.

```bash
docker build -t order-app:phase1 ./services/order
kind load docker-image order-app:phase1 --name musinsa-phase1
kubectl apply -k deploy/k8s/legacy
kubectl apply -k deploy/k8s/new
```

- MySQL `mysql:8.4` — `strategy: Recreate`, emptyDir, init SQL은 `configMapGenerator`로 만든
  ConfigMap을 `/docker-entrypoint-initdb.d`에 마운트
- readiness probe는 `mysqladmin ping -h 127.0.0.1`. `-h`로 TCP를 강제하는 것이 핵심이다.
  MySQL 이미지는 초기화 중 `--skip-networking`으로 임시 서버를 띄우므로,
  init SQL이 끝나기 전에는 이 ping이 실패한다. 즉 readiness = "스키마까지 준비됨"
- Order는 initContainer `wait-for-mysql`(`until nc -z mysql 3306`)로 MySQL readiness 이후 기동
- `imagePullPolicy: IfNotPresent` — 이미지는 `kind load`로 노드 안에만 있다

```
$ kubectl get pods -n legacy
mysql-67b5b8558d-wvkt7   2/2     Running
order-c75df6655-pxcgh    2/2     Running
$ kubectl get pods -n new
mysql-67b5b8558d-k5d47   2/2     Running
order-c75df6655-p9dv7    2/2     Running
```

### 기능 확인 (port-forward)

legacy / new 양쪽 동일한 결과.

```
POST /api/orders   -> HTTP 201
  {"id":1,"productId":"P-1","quantity":2,"unitPrice":15000,"totalAmount":30000,
   "status":"CREATED","createdAt":"2026-09-01T00:00:00Z"}
GET  /api/orders/1    -> HTTP 200 (같은 본문)
GET  /api/orders/9999 -> HTTP 404
```

`createdAt`이 `APP_FIXED_CLOCK` 값(`2026-09-01T00:00:00Z`)으로 고정된다. DB 저장값도 UTC 그대로다.

```
$ mysql -e "SELECT id, product_id, created_at FROM orders"
1  P-1  2026-09-01 00:00:00.000000
```

### S0 리셋 확인

```
$ kubectl rollout restart deployment/mysql -n new     # 리셋 전: 주문 1건, next_id=2
$ kubectl rollout status  deployment/mysql -n new
deployment "mysql" successfully rolled out

$ mysql -e "SELECT COUNT(*) FROM orders"   -> 0
$ AUTO_INCREMENT                           -> 1
```

readiness를 통과한 뒤 앱 쪽에서도 확인했다.

- `GET /api/orders/1` → 404 (데이터가 사라짐)
- `POST /api/orders` → 201, **`id` = 1** (앱이 커넥션을 복구하고 auto-increment도 초기화됨)
- 같은 시각 `legacy`의 `GET /api/orders/1`은 200 그대로 — 두 스택의 DB가 독립적이다

## 1.3b 앱 배포 (메시 경유) — 미착수

## 1.4 관측: OTel Collector + Jaeger — 미착수

## 1.5 격리 (Fail-closed) — 미착수

결과는 `docs/isolation-proof.md`에 별도로 기록한다.

## 1.6 Shadow 미러링 스모크 — 미착수
