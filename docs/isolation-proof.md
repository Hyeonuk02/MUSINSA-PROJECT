# 격리 증명 (Phase 1.5)

`new` 네임스페이스가 클러스터 밖으로 나가지 못한다는 것을 보인다.
핵심은 "막혔다" 하나가 아니라 **막은 주체가 둘이고 각각의 실패 서명이 다르다**는 것이다.

| | 막는 주체 | 성격 | 실패 서명 |
|---|---|---|---|
| 테스트① | Istio `REGISTRY_ONLY` + `Sidecar` | **guardrail** — 미등록 의존성을 드러냄 | 즉시(≈10ms) 거부. HTTP는 502, HTTPS는 TCP 블랙홀 |
| 테스트② | Kubernetes NetworkPolicy | **경계** — 실제 격리 | HTTP 응답 없이 TCP 타임아웃(15s) |

**REGISTRY_ONLY를 격리의 근거로 쓰지 않는다.** sidecar를 우회하면 그만이기 때문이다.
①은 "guardrail이 동작한다"의 증거이고, 격리 증명은 ②다.

환경: kind `musinsa-phase1`, Kubernetes v1.35.8, Istio 1.31.1
(자세한 버전은 `docs/phase1-result.md`)

---

## 구성

### 1. WireMock — 허용된 목적지

`deploy/k8s/new/wiremock.yaml`. `new`는 `istio-injection=enabled`이므로 sidecar가 자동 주입된다(`2/2`).
스텁은 `GET /ping` → 200 `pong` 하나뿐이다.

"전부 막혔다"가 아니라 "밖은 막히고 안은 통한다"를 보이기 위한 대조군이다.

### 2. Istio guardrail

`deploy/k8s/istio/istio-install.yaml` (meshConfig)

```yaml
outboundTrafficPolicy:
  mode: REGISTRY_ONLY
accessLogFile: /dev/stdout    # default 프로파일은 access log가 꺼져 있다
```

`deploy/k8s/istio/sidecar-new.yaml`

```yaml
apiVersion: networking.istio.io/v1
kind: Sidecar
metadata:
  name: default
  namespace: new
spec:
  egress:
    - hosts:
        - "./*"              # 같은 네임스페이스 (Order, MySQL, WireMock)
        - "istio-system/*"   # istiod xDS
        - "observability/*"  # OTel Collector
        - "verify/*"         # Phase 2 검증 컴포넌트
```

### 3. 검증용 pod 두 개

`deploy/k8s/tools/curl-isolation-new.yaml`. 두 실패 서명을 분리하려면 sidecar가 있는 것과
없는 것이 각각 필요하다. Order 앱 이미지에는 curl이 없고, 앱 컨테이너에 exec하는 것도 피한다.

```
$ kubectl get pods -n new -l 'app in (isolation-injected,isolation-uninjected)'
NAME                   READY   STATUS
isolation-injected     2/2     Running     <- sidecar 있음
isolation-uninjected   1/1     Running     <- sidecar.istio.io/inject: "false"
```

---

## 테스트① — guardrail (NetworkPolicy 적용 **전**)

```bash
kubectl exec -n new isolation-injected -c curl -- \
  curl -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" --max-time 15 http://example.com
kubectl exec -n new isolation-injected -c curl -- \
  curl -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" --max-time 15 https://example.com
```

```
http://example.com
  http_code=502 time=0.019919s
  curl exit=0

https://example.com
  curl: (35) TLS connect error: error:00000000:lib(0)::reason(0)
  http_code=000 time=0.010331s
  curl exit=35
```

평문 HTTP와 HTTPS의 결과가 다르다. HTTP는 sidecar가 HTTP 레벨에서 가로채 502를 직접 돌려주고,
HTTPS는 내용을 볼 수 없으므로 TCP 레벨에서 블랙홀로 떨어져 연결이 끊긴다(curl 35).
**둘 다 즉시(≈10~20ms) 끝난다** — 패킷이 클러스터 밖으로 나갔다가 실패한 것이 아니라
sidecar가 그 자리에서 거부했기 때문이다.

### access log — 핵심 증거

```
$ kubectl logs -n new isolation-injected -c istio-proxy | grep -E "example.com|BlackHole"

[2026-09-28T07:46:27.295Z] "GET / HTTP/1.1" 502 - direct_response - "-" 0 0 0 - "-"
  "curl/8.11.1" "c9627983-150b-9809-b636-f342a4bb2aca" "example.com" "-" - -
  104.20.23.154:80 10.244.0.27:35284 - block_all

[2026-09-28T07:46:27.363Z] "- - -" 0 UH - - "-" 0 0 0 - "-" "-" "-" "-" "-"
  BlackHoleCluster - 104.20.23.154:443 10.244.0.27:49692 - -
```

- HTTPS(443): upstream cluster가 문자 그대로 **`BlackHoleCluster`**, 응답 플래그 `UH`(no healthy upstream)
- HTTP(80): route가 **`block_all`**, `direct_response`로 502.
  HTTP 레벨에서 막힌 경우 upstream 자체가 없으므로 로그에 `BlackHoleCluster` 대신 이 형태로 남는다.
  같은 guardrail의 두 표현이다.

### 허용 목적지는 통한다

```
$ kubectl exec -n new isolation-injected -c curl -- curl -sS http://wiremock.new.svc.cluster.local:8080/ping
pong
http_code=200
```

```
[2026-09-28T07:46:27.452Z] "GET /ping HTTP/1.1" 200 - via_upstream - "-" 0 4 37 37 "-"
  "curl/8.11.1" "..." "wiremock.new.svc.cluster.local:8080" "10.244.0.26:8080"
  outbound|8080||wiremock.new.svc.cluster.local ... - default
```

---

## NetworkPolicy 적용

`deploy/k8s/new/networkpolicy.yaml`. `podSelector: {}` → `new`의 모든 pod.
`Egress`만 지정하므로 Ingress(kubelet probe, 미러 트래픽 수신)는 제한하지 않는다.

허용 목록

| 대상 | 포트 | 이유 |
|---|---|---|
| `kube-system`의 `k8s-app=kube-dns` | UDP/TCP 53 | 이름은 풀리되 연결만 막히는 상태로 둔다. DNS까지 막으면 "이름을 못 찾음"으로 끝나 격리 증거가 약해진다 |
| `new` 전체 | — | Order ↔ MySQL, WireMock |
| `istio-system` | TCP 15012 | istiod xDS. 끊기면 제어면이 죽는다 |
| `observability` | TCP 4317 | OTel Collector. 끊기면 1.4의 trace가 사라진다 |
| `verify` | — | Phase 2 검증 컴포넌트 |

```
$ kubectl get networkpolicy -n new
NAME                  POD-SELECTOR   AGE
default-deny-egress   <none>         5s
```

---

## 테스트② — 격리 경계 (NetworkPolicy 적용 **후**, sidecar 없는 pod)

```bash
kubectl exec -n new isolation-uninjected -c curl -- \
  curl -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" --max-time 15 http://example.com
kubectl exec -n new isolation-uninjected -c curl -- \
  curl -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" --max-time 15 https://example.com
```

```
http://example.com
  http_code=000 time=15.002424s
  curl: (28) Connection timed out after 15002 milliseconds
  curl exit=28

https://example.com
  http_code=000 time=15.002896s
  curl: (28) Connection timed out after 15002 milliseconds
  curl exit=28
```

**HTTP 응답이 전혀 없고 TCP 연결이 타임아웃된다.** sidecar가 없으므로 Istio는 이 트래픽을
보지도 못한다. 막은 것은 NetworkPolicy다.

이름 해석은 되는데 연결만 안 되는 상태라는 것도 같이 확인했다 —
"네트워크가 막혔다"이지 "DNS가 고장났다"가 아니다.

```
$ kubectl exec -n new isolation-uninjected -c curl -- nslookup example.com
Name:	example.com
Address: 2606:4700:10::ac42:93f3
```

### 허용 목적지는 통한다

```
$ kubectl exec -n new isolation-uninjected -c curl -- curl -sS http://wiremock.new.svc.cluster.local:8080/ping
pong
http_code=200
```

### 두 서명의 대비

| | HTTP | HTTPS | 소요 |
|---|---|---|---|
| ① sidecar 있음 (guardrail) | 502 (`block_all`, `direct_response`) | curl 35, `BlackHoleCluster`/`UH` | ≈10~20ms |
| ② sidecar 없음 (NetworkPolicy) | curl 28, 응답 없음 | curl 28, 응답 없음 | 15s (타임아웃) |

NetworkPolicy 적용 **후**에 주입 pod로 같은 요청을 다시 보내면 ①의 서명이 그대로 유지된다
(sidecar가 더 앞에서 거부하므로 패킷이 NetworkPolicy까지 가지 않는다).

```
http  : http_code=502 time=0.005988s
https : curl: (35) TLS connect error   time=0.011153s

[2026-09-28T07:48:53.279Z] ... "example.com" ... - block_all
[2026-09-28T07:48:53.343Z] "- - -" 0 UH ... BlackHoleCluster - 104.20.23.154:443 ...
```

---

## 격리가 끊지 말아야 할 것 — 확인

격리는 외부만 끊어야 한다. 제어면과 관측면이 같이 죽으면 이후 단계가 성립하지 않는다.

**제어면** — `new`의 모든 sidecar가 istiod와 동기화 상태를 유지한다.

```
$ istioctl proxy-status | grep '\.new'
isolation-injected.new          1.31.1   4 (CDS,LDS,EDS,RDS)
mysql-59bd4bdd44-sdbkw.new      1.31.1   4 (CDS,LDS,EDS,RDS)
order-695d64976c-dnc9z.new      1.31.1   4 (CDS,LDS,EDS,RDS)
wiremock-565b9d9475-gt7q8.new   1.31.1   4 (CDS,LDS,EDS,RDS)
```

**애플리케이션** — `new`의 Order가 같은 네임스페이스 MySQL에 계속 접근한다.

```
$ kubectl exec -n legacy mesh-check -c curl -- curl -s http://order.new.svc.cluster.local:8080/api/orders/1
order.new 요청: 200
```

**관측면** — 1.4의 trace가 계속 Jaeger에 도착한다. 격리 적용 후 요청 1건의 trace:

```
traceId f495b612cd68f258699b9f261c7607be : span 7개
  [mesh-check.legacy] order.new.svc.cluster.local:8080/*    (클라이언트 Envoy)
  [order.new]         order.new.svc.cluster.local:8080/*    (new 쪽 Envoy)
  [order-new]         GET /api/orders/{id}
  [order-new]         OrderRepository.findById
  [order-new]         Session.find poc.order.Order
  [order-new]         SELECT orders.orders
  [order-new]         Transaction.commit
```

`new`의 Order sidecar가 Collector로 계속 전송 중이다.

```
outbound|4317||otel-collector.observability.svc.cluster.local ... rq_total::6
outbound|4317||otel-collector.observability.svc.cluster.local ... cx_connect_fail::0
outbound|4317||otel-collector.observability.svc.cluster.local ... health_flags::healthy
```

---

## 결론

- ① guardrail 동작: 즉시 거부, access log에 `BlackHoleCluster`(HTTPS) / `block_all`(HTTP)
- ② **격리 경계 성립**: sidecar가 없어도 TCP 연결 자체가 되지 않는다
- 두 실패의 서명이 서로 다르다 — 막은 주체를 구분할 수 있다
- 허용 목록(같은 네임스페이스·istiod·Collector·verify)은 정상 동작하며,
  제어면·애플리케이션·관측면 어느 것도 끊기지 않았다

---

# 스택 간 DB 격리 (Phase 2, 2.3 전)

Phase 1.3a는 **데이터 독립성**(new 리셋 시 legacy 불변)만 확인했고, 위 1.5는 `new`에서 **밖으로 나가는 것(egress)**만 다뤘다.
여기서는 legacy↔new 사이에서 상대 스택 DB에 **네트워크로 도달할 수 없음**을 보인다.
격리를 설정(JDBC URL)이 아니라 네트워크로 보장하는 이유는 decision-log D11.

측정 방법: `mysql:8.4` client로 **실제 로그인**(`select @@hostname`)을 시도한다.
curl `telnet://`은 쓰지 않았다. sidecar가 TCP를 로컬에서 먼저 받아 주고 MySQL은 서버가 먼저 말하는
프로토콜이라 연결 여부가 정확히 보이지 않았다(대조군조차 판정 불가).
client pod 매니페스트: `deploy/k8s/tools/mysql-probe.yaml`.

## 1차 측정 — 3번이 뚫려 있었다

NetworkPolicy는 `new/default-deny-egress` 하나뿐이었다.

| 시도 | 기대 | 결과 | 막은 주체 |
|---|---|---|---|
| ① `new` pod(비주입) → `mysql.legacy:3306` | 차단 | 차단 — `Connection timed out` | NetworkPolicy(new egress) |
| ② `new` pod(sidecar) → `mysql.legacy:3306` | 차단 | 차단 — `ERROR 2013 … reading initial communication packet`, access log `BlackHoleCluster UH` | Istio guardrail (Sidecar egress 허용 목록 밖) |
| ③ `legacy` pod → `mysql.new:3306` | 차단 | **접속 성공** — `select @@hostname` → new의 mysql pod 이름 | 없음 |

③은 new mysql sidecar의 inbound access log에도 legacy mysql pod IP에서 온 3306 연결이 정상 종료로 남았다.
legacy에는 egress 제한이 없고, new에는 ingress 제한이 없기 때문이다.

## 조치 — A: DB pod ingress를 소유 서비스로 좁힌다

`deploy/k8s/base/mysql-networkpolicy.yaml` (base에 두어 legacy/new 동일 적용)

```yaml
podSelector: { matchLabels: { app: mysql } }
policyTypes: [Ingress]
ingress:
  - from:
      - podSelector: { matchLabels: { app: order } }   # namespaceSelector 없음 = 같은 ns만
    ports: [{ port: 3306, protocol: TCP }]
```

- 허용 = **같은 네임스페이스의 소유 서비스(app=order)에서 3306만**. 같은 ns라도 다른 pod는 차단
- Phase 3에서 Coupon DB가 생기면 `app=<coupon-db>` ← `app=coupon` 형태로 같은 정책을 붙인다
- mysql readiness는 exec probe라 영향 없음. 적용 후 mysql `rollout restart`로 새로 뜬 pod도 2/2(istio-proxy readiness 포함)
- 검토한 대안: B(new ns 전체 default-deny ingress — 미러·probe 경로 재검증 범위가 큼), C(legacy egress 제한 — 운영 역할 쪽에 허용 목록 부담)

## 최종 측정 (조치 후)

교차 스택 시도에는 **소유 서비스 레이블(app=order)을 흉내 낸** client pod를 썼다 — 가장 강한 경우.
(probe pod는 readinessProbe를 항상 실패시켜 order Service endpoint에서 빠지게 했다.)

| 시도 | 기대 | 결과 | 막은 주체 |
|---|---|---|---|
| ① `new` pod(비주입, app=order) → `mysql.legacy:3306` | 차단 | 차단 — `ERROR 2003 … (110)`, 5s 타임아웃 | NetworkPolicy (new egress + legacy mysql ingress) |
| ② `new` pod(sidecar, app=order) → `mysql.legacy:3306` | 차단 | 차단 — `ERROR 2013 … reading initial communication packet`, 즉시 | Istio guardrail (+ 아래층 NetworkPolicy) |
| ③ `legacy` pod(sidecar, app=order) → `mysql.new:3306` | 차단 | **차단** — `ERROR 2013 … waiting for initial communication packet (110)`, 5s. new mysql inbound log에 해당 IP 없음 | NetworkPolicy (new mysql ingress) |
| ③' `legacy` mysql pod → `mysql.new:3306` (1차에서 뚫린 경로) | 차단 | 차단 — 동일 서명 | NetworkPolicy |

대조군

| 시도 | 기대 | 결과 |
|---|---|---|
| `legacy` pod(app=order) → `mysql.legacy` | 성공 | 성공 — legacy mysql pod 이름 |
| `new` pod(app=order) → `mysql.new` | 성공 | 성공 — new mysql pod 이름 |
| `legacy` pod(app=dbprobe) → `mysql.legacy` | 차단(소유 서비스 아님) | 차단 — `ERROR 2013 … (110)` |
| 실제 order 앱 → 자기 mysql (mysql 재시작 후 새 커넥션) | 성공 | 성공 — Ingress `GET /api/orders/by-key/…` 404(DB 조회 결과), new는 미러 수신 |

**통과**: 교차 스택 세 경우 모두 연결 실패, 대조군 정상.

## 측정 중 관찰 (격리와 무관, 기록)

- **비주입 client → sidecar가 있는 자기 mysql은 정책과 무관하게 실패한다.** 정책을 지운 상태에서도 같은
  `ERROR 2013 … (110)`이었다. MySQL은 서버가 먼저 greeting을 보내는데, PERMISSIVE mTLS의 inbound Envoy는
  평문/TLS를 판별하려고 클라이언트의 첫 바이트를 기다려 양쪽이 서로를 기다린다(server-first 프로토콜 제약).
  실제 order는 sidecar 주입 pod라 이 경로를 쓰지 않는다. 그래서 대조군은 sidecar pod로만 잡았다.
- **workload 인증서 만료로 메시 HTTP가 503 UC.** 측정 중 ingressgateway·mesh-check·isolation-injected 세 proxy의
  인증서가 갱신되지 않은 채 만료(`istioctl proxy-config secret` → `valid=false`, notAfter 2026-10-11 08:51~11:07Z)되어
  Ingress 포함 메시 HTTP 호출이 `503 UC`였다. NetworkPolicy를 지워도 동일해 정책과 무관함을 확인했고,
  세 pod 재시작으로 복구. agent 로그에 수 시간씩 빈 구간이 있어 호스트(Docker VM) sleep 동안 갱신 타이머가
  밀린 것으로 추정한다(검증은 안 함). 장시간 방치 후 run 전에는 `istioctl proxy-config secret`로 만료를 점검한다.
