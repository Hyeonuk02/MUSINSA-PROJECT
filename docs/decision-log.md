# Decision Log

구현 중 내린 결정을 **결정 / 근거 / 대안** 형식으로 남긴다.
"왜 이렇게 되어 있는지"를 나중에 되짚기 위한 것이고, 뒤집을 때도 여기서 시작한다.

전체 설계는 [architecture.md](architecture.md), 단계별 계획은 [phase1-plan.md](phase1-plan.md),
실행 결과는 [phase1-result.md](phase1-result.md), 격리 증명은 [isolation-proof.md](isolation-proof.md).

---

## Phase 1 — Kubernetes + Istio 기반

### D1. node 이미지를 `kindest/node:v1.35.8`로 고정

**결정**
kind v0.33.0이 제공하는 노드 이미지 중 `v1.35.8`을 digest까지 고정해서 쓴다.

```
kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0
```

**근거**
Kubernetes 버전은 혼자 정할 수 없고 위아래 두 제약 사이에 끼어 있다.

- 위: Istio 1.31.1의 공식 지원 범위가 **1.32 ~ 1.36**이다. kind가 주는 최신 이미지 `v1.37.0`은 범위 밖이라 제외된다.
- 아래: 로컬 `kubectl`이 v1.34.1이고 kubectl 스큐 정책은 ±1 minor다.

`v1.35.8`은 Istio 지원 범위 안이면서 kubectl과 1 minor 차이라 양쪽을 만족한다.
digest까지 고정하는 것은 kind 릴리스마다 같은 태그로 다른 이미지가 올라가기 때문이다.
태그만으로는 재현되지 않는다.

**대안**

- `v1.36.4` — Istio가 지원하는 가장 높은 버전. kubectl과 2 minor 차이라 스큐 범위 밖이고
  kubectl 업그레이드가 필요해진다. 검증 환경의 재현성을 위해 손대는 도구를 늘리지 않기로 했다.
- `v1.34.11` — kubectl과 정확히 일치. 지원 범위 하단에 붙어 Istio를 올릴 때 여유가 없다.
- 버전 고정 없이 최신 — 재현 불가. 이 프로젝트는 "같은 조건에서 두 번 돌리면 같은 결과"가 전제다.

---

### D2. kind에 `extraPortMappings`로 호스트 포트 80/443을 연다

**결정**
kind 노드에 `ingress-ready=true` 라벨을 붙이고 NodePort 대역을 호스트 포트에 매핑한다.
Istio Ingress Gateway는 `type: NodePort`(30080/30443) + `nodeSelector: ingress-ready=true`로 고정한다.

```
host 80  -> node 30080 -> istio-ingressgateway :80
host 443 -> node 30443 -> istio-ingressgateway :443
```

**근거**
kind에는 LoadBalancer 구현이 없어 기본 `type: LoadBalancer`면 Service가 `Pending`으로 남는다.
Phase 2에서 k6가 **클러스터 밖에서 Ingress로 반복 요청**하는데,
`kubectl port-forward`는 프로세스가 죽으면 끊기고 장시간 부하에서 불안정하다.
호스트 포트는 클러스터가 살아 있는 한 유지된다.

`extraPortMappings`는 **클러스터 생성 시점에만** 정할 수 있어 나중에 추가하려면 클러스터를 다시 만들어야 한다.
1.1에서 한 번 만든 뒤 이 결정 때문에 재생성했다.

**대안**

- `kubectl port-forward` — 추가 설정이 없지만 프로세스 의존. Phase 2의 반복 부하에 부적합.
- MetalLB 등 LoadBalancer 구현 설치 — 실제 LoadBalancer에 가깝지만
  검증 대상과 무관한 컴포넌트가 하나 늘어난다. Phase 1의 "바닥을 얇게"에 어긋난다.
- hostNetwork 게이트웨이 — 포트 충돌과 격리 문제가 생긴다.

---

### D3. MySQL readiness probe는 `-h 127.0.0.1`로 TCP를 강제한다

**결정**

```yaml
readinessProbe:
  exec:
    command: ["sh", "-c", 'mysqladmin ping -h 127.0.0.1 -u root -p"$MYSQL_ROOT_PASSWORD" --silent']
```

**근거**
`-h` 없이 ping하면 유닉스 소켓으로 붙는다. MySQL 공식 이미지는 초기화 중
`--skip-networking`으로 임시 서버를 띄워 `/docker-entrypoint-initdb.d`를 실행하는데,
이때 소켓은 이미 열려 있다. 소켓으로 보면 **스키마가 만들어지기 전에 ready가 되어버린다.**

`-h 127.0.0.1`로 TCP를 강제하면 init SQL이 끝나 정상 서버가 뜬 뒤에야 성공한다.
즉 readiness의 의미가 "프로세스가 떴다"가 아니라 **"스키마까지 준비됐다"** 가 된다.

이것은 `rollout restart` = S0 리셋이라는 성질과 직결된다.
리셋 후 readiness가 통과했는데 스키마가 없으면 다음 run이 깨진 상태에서 시작한다.

**대안**

- 소켓 ping — 위 이유로 부족하다.
- `SELECT 1` 같은 쿼리 probe — 더 정확하지만 명령이 길고 실패 원인이 섞인다.
  TCP 강제만으로 필요한 보장이 나온다.
- probe 없이 앱 쪽 재시도 — 기동 실패가 CrashLoopBackOff로 나타나 원인 파악이 어려워진다.

---

### D4. 스키마 소유자는 init SQL 하나, 앱은 DDL을 만들지 않는다

**결정**
DDL은 `deploy/k8s/base/mysql-initdb/schema.sql` 한 곳에만 둔다.
앱은 `spring.sql.init.mode: never`, `spring.jpa.hibernate.ddl-auto: none`.

**근거**
"emptyDir + init SQL 재실행 = S0 리셋"이 이 프로젝트의 리셋 정의다.
앱도 스키마를 만들면 리셋의 주체가 둘이 되어 그 정의가 흐려진다.
DDL 사본이 두 곳에 있으면 Phase 2에서 스키마가 바뀔 때 어긋난다.

Hibernate가 스키마를 만들거나 바꾸면 **Legacy와 New의 스키마가 코드에 따라 달라질 수 있다.**
그러면 관측된 차이가 코드 차이인지 스키마 차이인지 구분되지 않는다.
`ddl-auto: none`으로 Hibernate를 스키마에서 완전히 배제한다.

Phase 0(Postgres)에서 바뀐 것: `GENERATED ALWAYS AS IDENTITY` → `AUTO_INCREMENT`,
`TIMESTAMPTZ` → `DATETIME(6)`. MySQL에는 timezone-aware 타입이 없어
세션·JVM 타임존을 UTC로 고정하고 UTC 값을 그대로 저장한다.
`TIMESTAMP`는 2038년 상한이 있어 쓰지 않는다.

**대안**

- `ddl-auto: validate` — 스키마를 만들지는 않으면서 엔티티와 DDL의 불일치를 기동 시점에 잡아준다.
  Phase 2에서 스키마가 바뀌기 시작하면 다시 검토할 만하다. 현재는 `none`.
- 앱의 `schema.sql`을 유지(`mode: always`, `CREATE TABLE IF NOT EXISTS`) — 멱등이라 당장은 문제없지만
  사본이 둘이 되어 위 이유로 채택하지 않았다.
- 마이그레이션 도구(Flyway/Liquibase) — Phase 1에는 과하다. 스키마가 실제로 진화하면 그때.

---

### D5. OTel Java agent는 digest 고정 이미지에서 initContainer가 복사한다

**결정**
`ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java`를 digest로 고정하고,
initContainer가 공유 `emptyDir`로 `javaagent.jar`를 복사한다. 앱은 `JAVA_TOOL_OPTIONS`로 붙인다.
Legacy와 New는 **동일한 imageID**를 쓴다.

```yaml
initContainers:
  - name: otel-agent
    image: ghcr.io/.../autoinstrumentation-java@sha256:342ad4c7...
    command: ["cp", "/javaagent.jar", "/otel/javaagent.jar"]
```

**근거**
두 가지가 런타임 다운로드를 배제한다.

1. **격리와 충돌한다.** `new`에는 default-deny egress NetworkPolicy와 REGISTRY_ONLY가 걸린다.
   기동 시 jar를 받아오는 방식은 격리를 켜는 순간 깨진다.
   즉 "관측이 켜져 있으면 격리가 안 되고, 격리를 켜면 관측이 죽는" 구조가 된다.
2. **같은 조건이라는 전제가 깨진다.** 매번 받아오면 Legacy와 New가 같은 agent라는 보장이 없다.
   관측 결과의 차이가 코드 차이인지 도구 차이인지 구분되지 않는다.

이미지 pull은 kubelet이 노드에서 하므로 pod의 NetworkPolicy와 무관하다.
pod 안에서 받아오는 것과 다르다.

부수적으로 겪은 것: `kind load docker-image`는 멀티아치 이미지에서
`content digest ... not found`로 실패한다. `docker save --platform linux/arm64` 후
`kind load image-archive`로 넣고, 매니페스트가 참조하는 index digest는
노드에서 `crictl pull <image>@sha256:...`로 확보했다.

**대안**

- 앱 이미지에 agent를 넣어 빌드 — 다운로드가 없어 조건은 만족하지만
  agent를 올릴 때마다 앱 이미지를 다시 빌드해야 하고, 앱 코드와 관측 도구의 수명주기가 묶인다.
- OTel Operator의 자동 주입(`Instrumentation` CR) — 같은 initContainer 방식을 Operator가 해준다.
  Operator라는 컴포넌트가 하나 늘어 Phase 1의 범위를 넘는다. Phase 2 이후 재검토 가능.
- initContainer에서 `curl`로 jar 다운로드 — 위 두 이유로 배제.

---

### D6. 격리 경계는 NetworkPolicy, REGISTRY_ONLY는 guardrail

**결정**
`new`의 외부 차단은 Kubernetes NetworkPolicy(default-deny egress)로 만든다.
Istio `outboundTrafficPolicy: REGISTRY_ONLY` + `Sidecar` 리소스는 **미등록 의존성을 드러내는 장치**로만 쓰고,
격리의 근거로 인용하지 않는다.

**근거**
REGISTRY_ONLY는 sidecar를 통과하는 트래픽만 본다. sidecar가 없거나 우회하면 그대로 나간다.
Istio 문서도 이를 보안 경계로 쓰지 말라고 한다. 경계는 커널/CNI 레벨이어야 한다.

Phase 1.5에서 두 장치의 **실패 서명이 다르다**는 것을 실측해 구분했다.

| | 막는 주체 | HTTP | HTTPS | 소요 |
|---|---|---|---|---|
| ① sidecar 주입 pod, NetworkPolicy 전 | Istio (guardrail) | `502`, access log route `block_all` / `direct_response` | curl exit `35`, upstream `BlackHoleCluster`, 플래그 `UH` | ≈10~20ms |
| ② 비주입 pod, NetworkPolicy 후 | NetworkPolicy (경계) | curl exit `28`, 응답 없음 | curl exit `28`, 응답 없음 | 15s 타임아웃 |

①에서 HTTP와 HTTPS의 서명이 갈리는 것이 중요하다.
HTTP는 sidecar가 HTTP 레벨에서 가로채 502를 직접 돌려주므로 upstream이 없고,
로그에 `BlackHoleCluster` 대신 route `block_all`로 남는다.
**`BlackHoleCluster` 문자열만 찾으면 HTTP 쪽을 놓친다.**

NetworkPolicy에서 **kube-dns는 허용**한다. DNS까지 막으면 실패가 "이름을 못 찾음"으로 끝나
"네트워크가 막혔다"는 증거가 약해진다. 이름은 풀리고 연결만 안 되는 상태가 더 분명한 증거다.

허용 목록: kube-dns(53), `new` 전체, `istio-system` 15012(istiod xDS),
`observability` 4317(Collector), `verify`. 제어면과 관측면이 같이 죽으면 이후 단계가 성립하지 않는다.

**대안**

- REGISTRY_ONLY만으로 격리 — sidecar 우회로 뚫린다. 증명이 되지 않는다.
- NetworkPolicy만 쓰고 REGISTRY_ONLY는 빼기 — 경계로는 충분하지만
  "코드가 등록되지 않은 외부 의존성을 부르고 있다"를 조기에 드러내는 신호를 잃는다.
  두 장치는 목적이 다르므로 둘 다 둔다.
- Istio Egress Gateway — 기능이 늘고 Phase 1의 "Istio는 셋만" 원칙에 어긋난다.

---

### D7. meshConfig에 `accessLogFile: /dev/stdout`을 켠다

**결정**
`meshConfig.accessLogFile: /dev/stdout`을 추가한다.

**근거**
Istio `default` 프로파일은 Envoy access log가 **꺼져 있다.**
1.5의 완료 기준이 "access log에 `BlackHoleCluster`"인데, 로그가 없으면 증거 자체를 수집할 수 없다.

관측 대상이 앱 로그만은 아니다. Envoy가 무엇을 어디로 보냈고 왜 막았는지는
access log에만 남는다. 미러링·격리·판정을 다루는 프로젝트에서 이 정보 없이 원인을 좁히기 어렵다.
실제로 1.4의 span export 실패와 1.5의 차단 서명을 모두 이 로그로 확인했다.

**대안**

- 필요할 때만 임시로 켜기 — 문제가 생긴 뒤에는 이미 그 요청의 로그가 없다.
- `Telemetry` API의 access logging으로 세밀하게 제어 — Phase 2에서 로그량이 문제되면 검토.
  Phase 1 규모에서는 전역 stdout으로 충분하다.
- JSON 포맷 커스터마이즈 — Phase 2에서 Evidence로 파싱하게 되면 그때.

---

### D8. 미러 요청의 Host `-shadow` 접미사는 기본값(붙이지 않음)을 유지한다

**결정**
Istio 1.31의 기본 동작을 그대로 둔다. 미러 요청의 Host는 원본과 동일하다.

```
requestMirrorPolicies:
  - cluster: outbound|8080||order.new.svc.cluster.local
    disableShadowHostSuffixAppend: true      <- Istio 1.31 기본값
```

**근거**
예전 Envoy는 미러 요청의 Host/`:authority`에 `-shadow`를 붙였고,
설계 문서도 그 전제로 "`-shadow`는 비교에서 제외(정규화)"라고 적혀 있었다.
Istio 1.28에서 `DISABLE_SHADOW_HOST_SUFFIX`가 추가되며 기본 동작이 바뀌었고,
1.31에서는 접미사가 붙지 않는다. Phase 1.6에서 실측으로 확인했다.

기본값을 유지하는 이유는 **양쪽이 바이트 단위로 같은 요청을 받아야 하기 때문**이다.
인프라가 요청에 차이를 주입하면 그 차이가 Evidence 비교에서 거짓 차이로 잡힐 수 있다.
접미사가 없으면 Host 정규화 규칙 자체가 필요 없어져 비교 로직도 단순해진다.

잃는 것은 "New가 자기가 미러인지 Host만 보고 알 수 있다"는 성질인데,
이 프로젝트는 그것을 필요로 하지 않는다. 구분이 필요하면 클라이언트가 넣는 헤더
(Phase 1은 `X-Phase1-Smoke-Id`, Phase 2는 replayRequestId)를 쓴다.
이 헤더가 미러까지 복사되는 것은 1.6에서 확인했다.

**대안**

- istiod에 `DISABLE_SHADOW_HOST_SUFFIX=false`로 예전 동작 복원 —
  설계 문서 원문과 일치시킬 수 있지만, 위 이유로 요청 동일성을 깨는 쪽이라 택하지 않았다.
  New가 미러임을 인프라 레벨에서 알아야 할 요구가 생기면 다시 검토한다.
- VirtualService의 `headers.request.set`으로 직접 표시 주입 —
  같은 이유(요청에 차이를 주입)로 기본적으로 피한다.

이 결정에 따라 `architecture.md`의 1.2 표와 5.3 Normalization,
`phase1-plan.md`의 확정 사항과 1.6 기준을 실측대로 고쳤다.
