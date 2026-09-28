# Phase 1 실행 결과

`docs/phase1-plan.md`의 각 단계에 대한 확정 버전과 확인 결과를 기록한다.
결정의 근거와 검토한 대안은 [decision-log.md](decision-log.md)에 따로 있다.

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

## 1.3b 앱 배포 (메시 경유) — 완료

정의 파일: `deploy/k8s/tools/curl-mesh-check.yaml`

### 로그 헤더 목록 확장

`RequestLogFilter`는 `request-log.headers`에 나열된 헤더만 기록한다.
Envoy가 붙이는 `x-request-id`를 보려면 목록에 넣어야 한다.
앱 코드는 두지 않고 `deploy/k8s/base/order.yaml`의 env로 덮어쓴다 (legacy/new 공통).

```yaml
- name: REQUEST_LOG_HEADERS
  value: Content-Type,Idempotency-Key,x-request-id
```

1.6에서 `X-Phase1-Smoke-Id`를 같은 방식으로 추가한다.

### 검증용 curl pod

`legacy`는 `istio-injection=enabled`이므로 sidecar가 자동 주입된다 (`READY 2/2`).
Order 앱 이미지에는 curl이 없고 앱 컨테이너에 exec하는 것도 피한다.

`command: ["sleep", "infinity"]`를 쓴다. `sleep 3600`이면 한 시간 뒤 pod가
`Succeeded`로 끝나 `kubectl exec`이 안 된다 (1.2의 `inject-check`이 실제로 그렇게 끝났다).

### 메시 경유 호출

```
$ kubectl exec -n legacy mesh-check -c curl -- curl -s http://order.legacy.svc.cluster.local:8080/api/orders/1
{"id":1,"productId":"P-1",...,"createdAt":"2026-09-01T00:00:00Z"}   HTTP 200

$ kubectl exec -n legacy mesh-check -c curl -- curl -s http://order.new.svc.cluster.local:8080/api/orders/1
{"id":1,"productId":"P-2",...,"createdAt":"2026-09-01T00:00:00Z"}   HTTP 200
```

### Envoy가 넣은 x-request-id가 앱 로그에 보임

legacy 쪽 `REQUEST_LOG` 한 건 (new도 동일한 형태, 값만 다름):

```json
{
  "requestId": null,
  "seq": 1,
  "method": "GET",
  "uri": "/api/orders/1",
  "headers": {
    "Content-Type": [],
    "Idempotency-Key": [],
    "x-request-id": ["3762d7cb-ae60-47d9-a824-0ff7f1a64cc2"]
  },
  "arrivedAt": 1790577710394,
  "completedAt": 1790577710554
}
```

`requestId`(= `X-Replay-Request-Id`)는 아직 아무도 넣지 않으므로 `null`이 맞다.
클라이언트가 넣은 헤더가 미러까지 전달되는지는 1.6에서 `X-Phase1-Smoke-Id`로 확인한다.

### proxy-config

```
$ istioctl proxy-config routes mesh-check -n legacy
8080   order.legacy.svc.cluster.local:8080   order.legacy.svc.cluster.local., order + 2 more...   /*
8080   order.new.svc.cluster.local:8080      order.new.svc.cluster.local., order.new + 1 more...  /*

$ istioctl proxy-config clusters mesh-check -n legacy
order.legacy.svc.cluster.local   8080   outbound   EDS
order.new.svc.cluster.local      8080   outbound   EDS
```

### port-forward 결과와 대조

legacy·new 모두 port-forward 응답과 메시 경유 응답의 본문이 **문자열까지 동일**하다.

## 1.4 관측: OTel Collector + Jaeger — 완료

정의 파일: `deploy/k8s/observability/otel-collector.yaml`, `deploy/k8s/observability/jaeger.yaml`,
`deploy/k8s/istio/istio-install.yaml`(meshConfig), `deploy/k8s/istio/telemetry.yaml`

### 고정한 아티팩트 (런타임 다운로드 없음)

| 용도 | 이미지 | digest |
|---|---|---|
| OTel Java agent | `autoinstrumentation-java:2.31.1` | `sha256:342ad4c72909bb92b7cd6fa09d5fdd50f41879b5657329e729baeacb46d9a02e` |
| Collector | `otel/opentelemetry-collector:0.161.0` | `sha256:b6d2b9a85b1029d05b5ad913150c1f014eed4ae99be81a1813ca5ade4a191913` |
| Jaeger all-in-one (v2) | `jaegertracing/jaeger:2.21.0` | `sha256:3d0ac795ff98aa04d1be04311d2dac6c25b4bfc8322dc02e53bc5b170c5018c3` |

agent는 initContainer가 digest 고정 이미지에서 공유 `emptyDir`로 복사한다.
기동 중 인터넷에서 jar를 받지 않는다 — 1.5에서 `new`에 default-deny egress와
REGISTRY_ONLY가 걸리면 다운로드 방식은 그 순간 깨지고, 매번 받아오면 legacy/new가
같은 agent라는 보장도 사라진다.

`kind load docker-image`는 멀티아치 이미지에서 `content digest ... not found`로 실패했다.
`docker save --platform linux/arm64` → `kind load image-archive`로 넣고,
매니페스트가 참조하는 index digest는 노드에서 `crictl pull <image>@sha256:...`로 확보했다.

### 구성

- `observability`에 Collector(OTLP 수신 4317/4318 → OTLP exporter → Jaeger)와
  Jaeger all-in-one 기동. 둘 다 `Running`
- Istio 트레이싱 두 단계 모두 적용
  - `meshConfig.extensionProviders`에 `otel-tracing`(opentelemetry, Collector FQDN:4317)
  - `Telemetry`(`istio-system`, 메시 전역) `randomSamplingPercentage: 100`
  - Envoy 리스너에 provider가 실제로 내려온 것을 확인:
    `envoy.tracers.opentelemetry`, `serviceName: order.legacy`,
    cluster `outbound|4317||otel-collector.observability.svc.cluster.local`
- Order에 OTel Java agent 부착. legacy/new 모두 **동일 imageID**
  (`sha256:4b5bcab8506cb59d0804179e8bab7046f137acbdcc219bca415b355338a7c0c0`)
- 앱 기동 로그에 agent 부착 확인 (완료 기준)

  ```
  Picked up JAVA_TOOL_OPTIONS: -javaagent:/otel/javaagent.jar
  [otel.javaagent ...] io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.31.1
  ```

- 식별자: `OTEL_SERVICE_NAME` = `order-legacy` / `order-new`,
  `OTEL_RESOURCE_ATTRIBUTES` = `service.namespace=legacy|new` (overlay patch)
- **앱 span은 Jaeger에 도착한다.** Jaeger v2의 조회 API는 `/api/v3/*`다(`/api/services`는 404).
  `/api/v3/services` → `["order-new","order-legacy","jaeger"]`.
  한 trace 안에 Tomcat·Spring Data·Hibernate·JDBC span이 함께 있다

  ```
  service=order-legacy  span=GET /api/orders/{id}         parent=8e4e0898a5c9a882   <- 앱 밖(Envoy)
  service=order-legacy  span=OrderRepository.findById
  service=order-legacy  span=Session.find poc.order.Order
  service=order-legacy  span=SELECT orders.orders
  service=order-legacy  span=Transaction.commit
  ```

### 막혔던 지점과 원인 (해결됨)

앱 span의 루트에 **앱이 만들지 않은 parent span id**가 있으므로 Envoy는 span을 만들고
컨텍스트를 전파하고 있다. 그런데 Jaeger에 Envoy 서비스(`order.legacy`)가 나타나지 않고,
Collector의 debug exporter에도 `service.name=order-legacy`(앱)만 들어온다.

istio-proxy의 tracing 로그 레벨을 올려 원인을 확인했다.

```
$ kubectl exec -n legacy mesh-check -c istio-proxy -- pilot-agent request POST "logging?tracing=debug"

debug envoy tracing .../trace_exporter.h:42      Number of exported spans: 1
debug envoy tracing .../grpc_trace_exporter.cc:39
  OTLP trace export failed with status: Unavailable,
  message: upstream connect error or disconnect/reset before headers.
  reset reason: protocol error{upstream_reset_before_response_started{protocol_error}}
```

Envoy는 span을 내보내려 했고 Collector로 가는 커넥션도 healthy였지만
(`outbound|4317||otel-collector... rq_total::1`, `cx_connect_fail::0`),
**프로토콜이 어긋났다.**

Istio는 Service 포트의 **이름 접두사**로 프로토콜을 판별한다(`grpc-`, `http-`, `http2-`, `tcp-` …).
포트 이름을 `otlp-grpc`로 지어서 어떤 접두사에도 해당하지 않았고, 그 결과 HTTP/1.1로 취급되어
HTTP/2만 받는 OTLP gRPC 수신부와 맞지 않았다.
앱(OTel Java agent)의 export는 sidecar를 거치는 경로가 달라 영향을 받지 않아,
"앱 span만 도착하고 Envoy span은 사라지는" 모양이 됐다.

### 수정

`otel-collector.yaml`, `jaeger.yaml`의 포트 이름을 `otlp-grpc` → `grpc-otlp`,
`otlp-http` → `http-otlp`로 바꾸고 4317에 `appProtocol: grpc`를 명시했다.
적용 후 `export failed` 로그가 사라지고 Envoy span이 Collector에 도착한다.

```
$ kubectl logs -n observability deployment/otel-collector | grep -oE "service.name=[^ ]+" | sort | uniq -c
   1 service.name=mesh-check.legacy    <- 클라이언트 sidecar (Envoy)
   1 service.name=order.legacy         <- 서버 sidecar (Envoy)
   1 service.name=order-legacy         <- 앱 (OTel Java agent)
```

이 이름 규칙은 Istio 전반에 적용된다. 이후 단계에서 메시를 지나는 gRPC 포트를 추가할 때도
포트 이름을 `grpc-`로 시작하게 해야 한다.

### 완료 기준 확인

**(1) Envoy span과 앱 span이 한 trace** — 요청 1건, span 7개, service 3종

```
traceId d6029bc457dbb79fd205eb10de643771
- [mesh-check.legacy] order.legacy.svc.cluster.local:8080/*      (클라이언트 Envoy)
   - [order.legacy] order.legacy.svc.cluster.local:8080/*        (서버 Envoy)
      - [order-legacy] GET /api/orders/{id}                      (Tomcat)
         - [order-legacy] OrderRepository.findById               (Spring Data)
            - [order-legacy] Session.find poc.order.Order        (Hibernate)
               - [order-legacy] SELECT orders.orders             (JDBC)
         - [order-legacy] Transaction.commit
```

**(2) 샘플링 100%** — 요청 10건 → trace 10건, 10건 모두 Envoy 2종 + 앱 span을 포함

```
요청 10건에 대한 trace 수: 10
Envoy 2종 + 앱 이 모두 있는 trace 수: 10
```

**(3) 앱 기동 로그의 agent 부착** — 위 "완료된 것" 참조 (legacy/new 동일)

진단용으로 넣었던 Collector의 `debug` exporter는 제거했고
(파이프라인은 `receivers: [otlp] → processors: [batch] → exporters: [otlp]`),
istio-proxy의 `tracing`/`grpc` 로그 레벨도 `info`로 되돌렸다.

Jaeger 조회는 `kubectl port-forward -n observability svc/jaeger 16686:16686` 후
`http://localhost:16686`. **조회 API는 `/api/v3/*`다** (Jaeger v2. `/api/services`는 404).

## 1.5 격리 (Fail-closed) — 완료

전체 기록(명령·출력·로그 발췌)은 **[docs/isolation-proof.md](isolation-proof.md)** 에 있다. 요약만 적는다.

정의 파일: `deploy/k8s/new/wiremock.yaml`, `deploy/k8s/istio/sidecar-new.yaml`,
`deploy/k8s/new/networkpolicy.yaml`, `deploy/k8s/tools/curl-isolation-new.yaml`,
`deploy/k8s/istio/istio-install.yaml`(meshConfig)

| | 막는 주체 | 실패 서명 |
|---|---|---|
| ① sidecar 주입 pod, NetworkPolicy 전 | Istio `REGISTRY_ONLY` + `Sidecar` (guardrail) | 즉시(≈10~20ms). HTTP 502 + access log `block_all`, HTTPS curl 35 + `BlackHoleCluster`/`UH` |
| ② 비주입 pod, NetworkPolicy 후 | Kubernetes NetworkPolicy (경계) | HTTP 응답 없이 TCP 타임아웃 15s (curl 28), HTTP/HTTPS 동일 |

두 서명이 다르므로 막은 주체를 구분할 수 있다. **격리 증명은 ②다.**
REGISTRY_ONLY는 sidecar를 우회하면 그만이므로 격리의 근거로 쓰지 않는다.

- WireMock `GET /ping` → 200 `pong` — ①② 두 pod 모두 성공 (허용 목록 정상)
- `accessLogFile: /dev/stdout`을 meshConfig에 추가했다. default 프로파일은 access log가 꺼져 있어
  `BlackHoleCluster` 증거를 볼 수 없다
- NetworkPolicy 허용 목록: kube-dns(53 UDP/TCP), `new` 전체, `istio-system` 15012,
  `observability` 4317, `verify`. DNS를 허용해야 "이름은 풀리는데 연결이 안 된다"가 되어
  격리 증거가 분명해진다
- 격리가 끊지 않은 것: `new` sidecar 4개 모두 istiod와 SYNCED, Order→MySQL 정상(200),
  1.4의 trace가 계속 Jaeger 도착(span 7개, `order.new` Envoy + `order-new` 앱)

## 1.6 Shadow 미러링 스모크 — 완료

정의 파일: `deploy/k8s/istio/gateway.yaml`, `deploy/k8s/istio/virtualservice-shadow.yaml`

### 구성

`Gateway`(`istio-system`, `istio: ingressgateway`, port 80) +
`VirtualService`: `route → order.legacy`, `mirror → order.new`, `mirrorPercentage 100`.

진입은 1.1에서 만든 호스트 포트를 그대로 쓴다 — port-forward 없이 `http://localhost/`.

```
host 80 -> node 30080 -> istio-ingressgateway :80 -> Gateway/VirtualService
```

로그 헤더 목록에 `X-Phase1-Smoke-Id`와 `Host`를 추가했다 (`REQUEST_LOG_HEADERS` env).

### 실행

```bash
curl -i -X POST http://localhost/api/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Phase1-Smoke-Id: smoke-001' \
  -d '{"productId":"P-SHADOW","quantity":3,"unitPrice":1000}'
```

```
HTTP/1.1 201 Created
server: istio-envoy
x-envoy-upstream-service-time: 548

{"id":2,"productId":"P-SHADOW",...,"createdAt":"2026-09-01T00:00:00Z"}
```

응답은 **하나뿐이다.** 미러는 fire-and-forget이라 new의 응답은 버려진다.

### 완료 기준 확인

**(1) 양쪽 앱 로그에 같은 `X-Phase1-Smoke-Id`** — 클라이언트가 넣은 헤더가 미러까지 복사된다.
최종 검증이 의존하는 성질이다.

| | legacy | new |
|---|---|---|
| `X-Phase1-Smoke-Id` | `smoke-001` | `smoke-001` |
| `bodyHash` | `ff01057d…` | `ff01057d…` |
| `x-request-id` (관찰용) | `f030a528-…` | `f030a528-…` |
| `Host` | `localhost` | `localhost` |

두 번째 요청(`smoke-002`)에서도 동일하게 재현된다
(`smoke=smoke-002 host=localhost xrid=1ffa9e76 body=b864fff3` 양쪽 일치).

**(2) `x-request-id`** — 관찰용. 양쪽이 같았으므로 기록한다.
Envoy가 ingress에서 한 번 붙인 값이 route와 mirror 양쪽에 그대로 간다.

**(3) Host 접미사** — **Istio 1.31은 `-shadow`를 붙이지 않는다.**
mirror 정책에 `disableShadowHostSuffixAppend: true`가 기본으로 들어간다.

```
$ istioctl proxy-config route deployment/istio-ingressgateway -n istio-system -o json
requestMirrorPolicies:
  - cluster: outbound|8080||order.new.svc.cluster.local
    runtimeFraction: { numerator: 1000000, denominator: MILLION }
    disableShadowHostSuffixAppend: true      <- 기본값
```

Istio 1.28에서 `DISABLE_SHADOW_HOST_SUFFIX`가 추가되며 기본 동작이 바뀐 것이다.
**기본값을 유지하기로 정했다.** 양쪽이 바이트 단위로 같은 요청을 받아야
Host가 Evidence 비교에서 거짓 차이로 잡히지 않는다. 미러 여부를 구분해야 하면
클라이언트가 넣는 헤더(`X-Phase1-Smoke-Id`)를 쓴다.
예전 동작이 필요하면 istiod에 `DISABLE_SHADOW_HOST_SUFFIX=false`.
`docs/phase1-plan.md`의 해당 서술도 실측대로 고쳤다.

**(4) 클라이언트는 legacy 응답만 받음** — 위 응답 1건. 미러가 실제로 도달한 것은
new의 DB로 확인한다.

```
legacy: 1 P-1        2 P-SHADOW  3 P-SHADOW2
new   : 1 P-2        2 P-SHADOW  3 P-SHADOW2
              ^ 1.3a 리셋 때문에 다름     ^ 미러로 양쪽에 생성됨
```

`id=1`이 다른 것은 1.3a의 리셋 실험 때문이고 미러링과 무관하다.
미러로 들어온 `P-SHADOW`, `P-SHADOW2`는 양쪽에 같은 id로 생성됐다.

---

## Phase 1 종료

1.1 ~ 1.6 모두 완료. 태그 `phase1-done`.

| 단계 | 결과 |
|---|---|
| 1.1 클러스터/네임스페이스 | 완료 — NetworkPolicy 스모크 통과, 호스트 포트 80/443 매핑 |
| 1.2 Istio 설치/주입 | 완료 — 1.31.1, `analyze` 이슈 없음 |
| 1.3a 앱 배포(기능) | 완료 — MySQL 8 전환, 고정 시각, S0 리셋 |
| 1.3b 앱 배포(메시) | 완료 — `x-request-id` 확인 |
| 1.4 관측 | 완료 — Envoy+앱 한 trace, 샘플링 100% |
| 1.5 격리 | 완료 — [isolation-proof.md](isolation-proof.md) |
| 1.6 미러링 | 완료 — 같은 `X-Phase1-Smoke-Id`가 양쪽에 도달 |

### Phase 1에서 겪은 것 중 Phase 2에 영향 있는 것

- **Istio는 Service 포트 이름의 접두사로 프로토콜을 판별한다** (`grpc-`, `http-`, …).
  `otlp-grpc`처럼 접두사가 아니면 HTTP/1.1로 취급되어 gRPC가 깨진다 (1.4)
- **`istio-proxy`는 `.spec.initContainers`에 있다** (native sidecar). 주입 확인은 `READY 2/2`로 (1.2)
- **access log는 기본으로 꺼져 있다.** `meshConfig.accessLogFile` 필요 (1.5)
- **Jaeger v2의 조회 API는 `/api/v3/*`** (`/api/services`는 404) (1.4)
- **미러 요청의 Host에 `-shadow`가 붙지 않는다** (Istio 1.31 기본값) (1.6)
- **pod에 파일을 넣을 때 런타임 다운로드를 쓰지 않는다.** digest 고정 이미지 →
  initContainer가 공유 `emptyDir`로 복사. `new`는 egress가 막혀 있어 다운로드 방식은 깨진다 (1.4)
- **`kind load docker-image`는 멀티아치 이미지에서 실패한다.**
  `docker save --platform` → `kind load image-archive`, digest는 노드에서 `crictl pull` (1.4)

### 재현 절차

```bash
kind create cluster --config deploy/k8s/kind-config.yaml
kubectl apply -f deploy/k8s/00-namespaces.yaml
istioctl install -f deploy/k8s/istio/istio-install.yaml -y
kubectl label namespace legacy new istio-injection=enabled --overwrite
kubectl label namespace observability verify default istio-injection=disabled --overwrite
kubectl apply -f deploy/k8s/istio/telemetry.yaml
kubectl apply -f deploy/k8s/observability/

docker build -t order-app:phase1 ./services/order
kind load docker-image order-app:phase1 --name musinsa-phase1
kubectl apply -k deploy/k8s/legacy
kubectl apply -k deploy/k8s/new

kubectl apply -f deploy/k8s/new/wiremock.yaml
kubectl apply -f deploy/k8s/istio/sidecar-new.yaml
kubectl apply -f deploy/k8s/new/networkpolicy.yaml
kubectl apply -f deploy/k8s/istio/gateway.yaml -f deploy/k8s/istio/virtualservice-shadow.yaml
```

검증용 pod는 `deploy/k8s/tools/`에 따로 있다 (애플리케이션 스택이 아니므로 overlay에 넣지 않는다).
